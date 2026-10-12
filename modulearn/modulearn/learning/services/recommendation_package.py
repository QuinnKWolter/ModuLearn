"""Portable, URL-addressed recommendation packages; one atomic installation."""
import hashlib
import json
import re
import csv
import io
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.db import transaction

from courses.models import Course, Module, StaticRecommendationSet, Unit
from .course_plugins import normalize_course_plugin_config
from .recommendation_rollout import transition_recommendations
from .recommendation_sessions import resolve_session

FORMAT = 'modulearn.recommendations.v1'
CSV_FORMAT = 'modulearn.recommendations.csv.v1'
CSV_COLUMNS = ['format', 'source_id', 'source_title', 'source_unit', 'source_provider', 'source_url', 'source_protocols',
               'target_id', 'target_title', 'target_unit', 'target_provider', 'target_url', 'target_protocols',
               'type', 'rank', 'incorrect_attempts', 'per_type']


def is_linked_csv(raw):
    try:
        header = next(csv.reader(io.StringIO(raw.decode('utf-8-sig'))), [])
        return bool({'source_url', 'target_url'} & set(header))
    except (UnicodeError, csv.Error):
        return False


def csv_to_package(raw):
    """One explicit URL-addressed recommendation per row, no title guessing."""
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError('Recommendation files must be under 10 MiB.')
    try:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
        if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)) or set(reader.fieldnames) != set(CSV_COLUMNS):
            raise ValueError('Use the linked recommendation CSV columns documented in recommendation-package-format.md.')
        activities, links, settings = {}, [], None
        for row in reader:
            if len(links) >= 20000 or None in row or any(v is None for v in row.values()) or row['format'] != CSV_FORMAT:
                raise ValueError('Invalid or oversized linked recommendation CSV.')
            row_settings = {'incorrect_attempts': int(row['incorrect_attempts']), 'per_type': int(row['per_type'])}
            if settings is not None and settings != row_settings:
                raise ValueError('Delivery settings must be identical on every row.')
            settings = row_settings
            for prefix in ['source', 'target']:
                activity = {field: row[f'{prefix}_{field}'] for field in ['id', 'title', 'unit', 'provider', 'url']}
                activity['protocols'] = row[f'{prefix}_protocols'].split('|')
                key = activity['id']
                if key in activities and activities[key] != activity:
                    raise ValueError(f'{key}: conflicting activity details across CSV rows.')
                activities[key] = activity
            links.append({'source': row['source_id'], 'target': row['target_id'], 'type': row['type'], 'rank': int(row['rank'])})
        package = {'format': FORMAT, 'activities': list(activities.values()), 'recommendations': links, 'settings': settings or {}}
        converted = json.dumps(package, ensure_ascii=False).encode('utf-8')
        parse_package(converted)
        return converted
    except (UnicodeError, csv.Error) as exc:
        raise ValueError('Expected a valid UTF-8 linked recommendation CSV.') from exc


def install_csv_package(course_id, raw, *, actor, course_instance_id=None):
    return install_package(course_id, csv_to_package(raw), actor=actor, course_instance_id=course_instance_id,
                           source_sha256=hashlib.sha256(raw).hexdigest(), source_format=CSV_FORMAT)


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
def install_package(course_id, raw, *, actor, course_instance_id=None, source_sha256=None, source_format=FORMAT):
    instance = resolve_session(course_id, course_instance_id)
    activities, edges, sources, options = parse_package(raw)
    course = Course.objects.select_for_update().get(pk=course_id)
    if course.is_locked_for_research:
        raise ValueError('Research-locked courses cannot import recommendation packages.')
    digest = source_sha256 or hashlib.sha256(raw).hexdigest()
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
    dataset = StaticRecommendationSet.objects.filter(course_instance=instance).first()
    previous_bindings = dataset.bindings if dataset else {}
    bindings, created, source_placements = {}, [], {}
    for key in sorted(activities, key=lambda k: k not in sources):
        item = activities[key]
        identity = canonical_url(item['url'])
        candidates = by_url.get(identity, [])
        if candidates:
            if key in sources:
                candidates = [m for m in candidates if not m.is_recommendation_only]
                if not candidates:
                    raise ValueError(f"{item['title']}: a triggering problem is currently practice-only.")
                source_placements[key] = sorted(m.pk for m in candidates)
            # A URL identifies content; repeated placements are not distinct exercises.
            # Keep a previous binding stable, otherwise choose deterministically.
            module = min(candidates, key=lambda m: (
                m.pk != previous_bindings.get(key),
                not (m.is_visible and m.unit.is_visible),
                m.unit.title.casefold() != item['unit'].casefold(),
                m.is_recommendation_only, m.pk))
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
        if key in sources:
            source_placements.setdefault(key, [module.pk])
    nodes = {key: {'title': a['title'], 'provider': a['provider'], 'topic': a['unit'], 'clusters': []} for key, a in activities.items()}
    for key, placements in source_placements.items():
        nodes[key]['source_module_ids'] = placements
    defaults = {'course': course, 'enabled': True, 'nodes': nodes, 'edges': edges, 'bindings': bindings, 'options': options,
                'analysis': {'code': {k: a.get('code', '') for k, a in activities.items()}},
                'provenance': [{'kind': 'package', 'name': source_format, 'sha256': digest, 'rows': len(edges), 'ranking': 'explicit_rank'}]}
    unchanged = dataset is not None and all(getattr(dataset, k) == v for k, v in defaults.items())
    if not unchanged:
        StaticRecommendationSet.objects.update_or_create(course_instance=instance, defaults=defaults)
    plan = transition_recommendations(course.pk, course_instance_id=instance.pk)
    transition_recommendations(course.pk, course_instance_id=instance.pk, apply=True, expected_plan=plan['plan_sha256'])
    report = {'course_instance_id': instance.pk, 'sha256': digest, 'created_modules': created, 'activities': len(nodes), 'links': len(edges),
              'assignments_changed': plan['assignments_changed'], 'unchanged': unchanged}
    LogEntry.objects.create(user_id=actor.pk, content_type=ContentType.objects.get_for_model(course),
        object_id=str(course.pk), object_repr=str(course)[:200], action_flag=CHANGE,
        change_message=json.dumps({'recommendation_package_import': report}))
    return report
