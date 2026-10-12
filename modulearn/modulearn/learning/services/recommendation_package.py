"""Portable, URL-addressed recommendation packages; one atomic installation."""
import hashlib
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.db import transaction

from courses.models import Course, Module, StaticRecommendationSet, Unit
from .course_plugins import normalize_course_plugin_config
from .recommendation_rollout import transition_recommendations

FORMAT = 'modulearn.recommendations.v1'


def canonical_url(value):
    URLValidator(schemes=['https', 'http'])(value)
    parsed = urlsplit(value)
    if parsed.username or parsed.password:
        raise ValueError('Activity URLs must not contain credentials.')
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path,
                       urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True))), parsed.fragment))


def parse_package(raw):
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError('Recommendation packages must be under 10 MiB.')
    try:
        data = json.loads(raw.decode('utf-8-sig'))
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Expected a UTF-8 JSON recommendation package.') from exc
    if not isinstance(data, dict) or data.get('format') != FORMAT:
        raise ValueError(f'Expected format {FORMAT}.')
    activities, recommendations = data.get('activities'), data.get('recommendations')
    if not isinstance(activities, list) or not 1 <= len(activities) <= 5000:
        raise ValueError('Include 1–5000 activities.')
    if not isinstance(recommendations, list) or not 1 <= len(recommendations) <= 20000:
        raise ValueError('Include 1–20000 recommendation links.')
    indexed, urls = {}, set()
    for activity in activities:
        if not isinstance(activity, dict):
            raise ValueError('Each activity must be an object.')
        key = activity.get('id')
        if not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}', key) or key in indexed:
            raise ValueError('Activity IDs must be unique, nonempty identifiers.')
        for field in ('title', 'unit', 'provider'):
            value = activity.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > 255:
                raise ValueError(f'{key}: {field} must be 1–255 characters.')
        if not isinstance(activity.get('url'), str):
            raise ValueError(f'{key}: a delivery URL is required.')
        if len(activity['url']) > Module._meta.get_field('content_url').max_length:
            raise ValueError(f'{key}: delivery URLs must be at most 200 characters.')
        identity = canonical_url(activity['url'])
        if identity in urls:
            raise ValueError('Use one activity ID per delivery URL; reference that ID in every applicable link.')
        urls.add(identity)
        protocols = activity.get('protocols')
        if not isinstance(protocols, list) or not protocols or any(p not in ['splice', 'html', 'pitt', 'lti'] for p in protocols):
            raise ValueError(f'{key}: specify supported protocols.')
        if not isinstance(activity.get('code', ''), str):
            raise ValueError(f'{key}: code must be text.')
        indexed[key] = activity
    edges, ranks, pairs, sources = [], set(), set(), set()
    for link in recommendations:
        if not isinstance(link, dict):
            raise ValueError('Each recommendation must be an object.')
        source, target, kind, rank = (link.get(k) for k in ('source', 'target', 'type', 'rank'))
        if not isinstance(source, str) or not isinstance(target, str) or source not in indexed or target not in indexed or source == target:
            raise ValueError('Every link must reference two different, defined activity IDs.')
        kinds = {'animation': 'animatedexamples', 'worked_example': 'pcex', 'completion_problem': 'quizjet'}
        if not isinstance(kind, str) or kind not in kinds or type(rank) is not int or not 1 <= rank <= 1000:
            raise ValueError('Links require an activity type and a positive integer rank (1–1000).')
        if (source, kind, rank) in ranks or (source, target) in pairs:
            raise ValueError('Duplicate recommendation or rank for a problem/type.')
        ranks.add((source, kind, rank)); pairs.add((source, target)); sources.add(source)
        # Existing delivery stores a sortable score; package authors need only rank.
        edges.append({'source': source, 'target': target, 'provider': kinds[kind], 'rank': rank, 'similarity': 1 / rank})
    if set(indexed) != sources | {e['target'] for e in edges}:
        raise ValueError('Every activity must be referenced by a recommendation link.')
    settings = data.get('settings', {})
    if not isinstance(settings, dict):
        raise ValueError('Settings must be an object.')
    threshold, limit = settings.get('incorrect_attempts', 1), settings.get('per_type', 2)
    if type(threshold) is not int or not 1 <= threshold <= 100 or type(limit) is not int or not 1 <= limit <= 30:
        raise ValueError('Settings require incorrect_attempts 1–100 and per_type 1–30.')
    return indexed, edges, sources, {'trigger': 'needs_practice', 'failure_threshold': threshold,
                                   'limit': limit, 'minimum_similarity': None}


@transaction.atomic
def install_package(course_id, raw, *, actor):
    activities, edges, sources, options = parse_package(raw)
    course = Course.objects.select_for_update().get(pk=course_id)
    if course.is_locked_for_research:
        raise ValueError('Research-locked courses cannot import recommendation packages.')
    digest = hashlib.sha256(raw).hexdigest()
    existing = list(Module.objects.filter(unit__course=course).select_related('unit'))
    units = list(course.units.all())
    by_url = {}
    for module in existing:
        if module.content_url:
            try:
                by_url.setdefault(canonical_url(module.content_url), []).append(module)
            except (ValueError, ValidationError):
                # Unrelated legacy content may have a non-URL resource location.
                continue
    bindings, created = {}, []
    for key in sorted(activities, key=lambda k: k not in sources):
        item = activities[key]
        identity = canonical_url(item['url'])
        candidates = by_url.get(identity, [])
        if len(candidates) > 1:
            candidates = [m for m in candidates if m.unit.title.casefold() == item['unit'].casefold()]
            if len(candidates) != 1:
                raise ValueError(f"{item['title']}: multiple placements have this URL. Specify a unique unit placement first.")
        if candidates:
            module = candidates[0]
            if key in sources and module.is_recommendation_only:
                raise ValueError(f"{item['title']}: a triggering problem is currently practice-only.")
        else:
            matching_units = [u for u in units if u.title.casefold() == item['unit'].casefold()]
            if len(matching_units) > 1:
                raise ValueError(f"Ambiguous unit: {item['unit']}.")
            unit = matching_units[0] if matching_units else None
            if unit is None:
                unit = Unit.objects.create(course=course, title=item['unit'], order=max((u.order for u in units), default=0) + 10)
                units.append(unit)
            # Never silently replace a same-title activity with different content.
            if any(m.unit_id == unit.pk and m.title.casefold() == item['title'].casefold() for m in existing):
                raise ValueError(f"{item['title']}: an existing same-title activity has a different URL. Review its identity before importing.")
            module = Module.objects.create(unit=unit, title=item['title'], content_url=item['url'],
                provider_id=item['provider'], supported_protocols=item['protocols'],
                module_type=Module.MODULE_TYPE_SPLICE_SMART_CONTENT,
                is_recommendation_only=key not in sources,
                order=max((m.order for m in existing if m.unit_id == unit.pk), default=0) + 10,
                content_data={'recommendation_package': {'format': FORMAT, 'activity_id': key}})
            existing.append(module); by_url.setdefault(identity, []).append(module); created.append(module.pk)
        bindings[key] = module.pk
    nodes = {key: {'title': a['title'], 'provider': a['provider'], 'topic': a['unit'], 'clusters': []} for key, a in activities.items()}
    defaults = {'nodes': nodes, 'edges': edges, 'bindings': bindings, 'options': options,
                'analysis': {'code': {k: a.get('code', '') for k, a in activities.items()}},
                'provenance': [{'kind': 'package', 'name': FORMAT, 'sha256': digest, 'rows': len(edges), 'ranking': 'explicit_rank'}]}
    dataset = StaticRecommendationSet.objects.filter(course=course).first()
    unchanged = dataset is not None and all(getattr(dataset, k) == v for k, v in defaults.items())
    if not unchanged:
        StaticRecommendationSet.objects.update_or_create(course=course, defaults=defaults)
    course.plugin_config = normalize_course_plugin_config(course.plugin_config)
    course.plugin_config['plugins']['static_recommendations']['enabled'] = True
    course.save(update_fields=['plugin_config'])
    plan = transition_recommendations(course.pk)
    transition_recommendations(course.pk, apply=True, expected_plan=plan['plan_sha256'])
    report = {'sha256': digest, 'created_modules': created, 'activities': len(nodes), 'links': len(edges),
              'assignments_changed': plan['assignments_changed'], 'unchanged': unchanged}
    LogEntry.objects.create(user_id=actor.pk, content_type=ContentType.objects.get_for_model(course),
        object_id=str(course.pk), object_repr=str(course)[:200], action_flag=CHANGE,
        change_message=json.dumps({'recommendation_package_import': report}))
    return report
