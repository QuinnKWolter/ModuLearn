"""Durable remedial practice, isolated from course completion and grade passback."""
import hashlib
import json
import math

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.urls import reverse

from courses.models import (ModuleProgress, RecommendationActivation, RecommendationProgress,
                            RecommendationEvent, StaticRecommendationSet)
from .static_recommendations import resolve_nodes, source_keys_by_module
from .recommendation_sessions import recommendations_enabled


def attempt_snapshot(source, payload, score, success, event_type):
    """Read the current submission, never a provider's accumulated best grade."""
    data = payload if isinstance(payload, dict) else {}
    identity = None
    if source == 'cupcake':
        message = data.get('cupcake', {})
        if message.get('eventName') != 'answerChecked' or message.get('activityType') not in {'code-completion', 'parameterized-code-tracing', 'free-coding'}:
            return None
        identity = data.get('transport_id')
    elif source == 'pcex' and isinstance(data.get('pcex_result'), dict):
        raw = data['pcex_result']
        success = str(raw.get('result', '')).lower() in {'1', 'true'} or raw.get('result_type') == 'correct'
        score = 100.0 if success else 0.0
        if raw.get('attempt_count'):
            identity = raw
    elif source == 'pcrs' and isinstance(data.get('pcrs_result'), dict):
        raw = data['pcrs_result']
        maximum = float(raw.get('max_score') or 0)
        if maximum <= 0:
            return None
        score = 100 * float(raw.get('score') or 0) / maximum
        success = score >= 100
    elif source == 'acos_pcex' and data.get('acos_pcex_event', {}).get('event') == 'grade':
        raw = data['acos_pcex_event']['payload']
        maximum = float(raw.get('max_points') or 0)
        if maximum <= 0:
            return None
        score = 100 * float(raw.get('points') or 0) / maximum
        success = score >= 100
        if raw.get('attempt_count') or raw.get('event_data', {}).get('attempt_count'):
            identity = raw
    elif source == 'quizjet' and score is not None:
        pass
    elif source == 'splice' and score is not None:
        # PCEX uses the authoritative proxy callback; its SPLICE notification is
        # a duplicate, not an additional attempt.
        if data.get('trackingData'):
            return None
    else:
        return None
    if score is None or not math.isfinite(float(score)):
        return None
    key = hashlib.sha256(json.dumps([source, identity], sort_keys=True).encode()).hexdigest() if identity else None
    return {'score': max(0, min(100, float(score))), 'success': bool(success), 'key': key}


@transaction.atomic
def observe_source_attempt(progress, *, source, payload, score, success, event_type):
    if not progress.enrollment_id:
        return
    course = progress.enrollment.course_instance.course
    if not recommendations_enabled(progress.enrollment.course_instance):
        return
    attempt = attempt_snapshot(source, payload, score, success, event_type)
    if not attempt:
        return
    activation = RecommendationActivation.objects.filter(enrollment=progress.enrollment, source_module=progress.module).first()
    # Frozen assignments need no graph reload, and their follow-up attempts
    # remain research data even if an instructor later replaces the dataset.
    if not activation or not activation.activated_at:
        dataset = StaticRecommendationSet.objects.filter(course_instance=progress.enrollment.course_instance).defer('analysis').first()
        if not dataset:
            return
        resolved, _, modules = resolve_nodes(dataset, course)
        keys = source_keys_by_module(dataset, resolved, modules).get(progress.module_id, set())
        edges = [edge for edge in dataset.edges if edge['source'] in keys]
        if not edges:
            return
        activation, _ = RecommendationActivation.objects.get_or_create(enrollment=progress.enrollment, source_module=progress.module)
    activation = RecommendationActivation.objects.select_for_update().get(pk=activation.pk)
    if attempt['key'] and activation.events.filter(event_key=attempt['key']).exists():
        return
    RecommendationEvent.objects.create(activation=activation, event_type='source_attempt', source=source,
        event_key=attempt['key'], score=attempt['score'], success=attempt['success'], payload=payload or {})
    if not attempt['success']:
        activation.failures += 1
        activation.save(update_fields=['failures'])
    if activation.activated_at:
        return
    threshold = max(1, int(dataset.options.get('failure_threshold', 1)))
    if activation.failures < threshold:
        return
    candidates = select_candidates(dataset, resolved, edges, progress.module_id)
    if not candidates:
        return
    activation.activated_at = timezone.now()
    activation.configuration = {'options': dataset.options, 'provenance': dataset.provenance,
                                'dataset_revision': dataset.updated_at.isoformat(), 'failure_threshold': threshold,
                                'limit_scope': 'per_activity_type'}
    activation.save(update_fields=['activated_at', 'configuration'])
    for target, edge in candidates:
        RecommendationProgress.objects.create(activation=activation, module=target, provider=edge['provider'],
            rank=edge['rank'], similarity=edge['similarity'])
    RecommendationEvent.objects.create(activation=activation, event_type='activated', source='static_recommendations',
        payload={'failures': activation.failures, 'configuration': activation.configuration,
                 'items': [{'module_id': target.pk, 'title': target.title, 'provider': edge['provider'],
                            'rank': edge['rank'], 'similarity': edge['similarity']}
                           for target, edge in candidates]})


def select_candidates(dataset, resolved, edges, source_module_id):
    """Shared selection for new assignments and explicit dataset transitions."""
    minimum = dataset.options.get('minimum_similarity')
    candidates, seen, provider_counts = [], set(), {}
    limit = max(1, int(dataset.options.get('limit', 2)))
    disabled = set(dataset.options.get('disabled_targets', []))
    for edge in sorted(edges, key=lambda e: (-e['similarity'], e['rank'], e['target'])):
        target = resolved.get(edge['target'])
        if (edge['target'] in disabled or not target or target.pk == source_module_id or target.pk in seen
                or edge['provider'] not in {'animatedexamples', 'pcex', 'quizjet'}
                or provider_counts.get(edge['provider'], 0) >= limit
                or not target.is_visible or not target.unit.is_visible
                or (minimum is not None and edge['similarity'] < minimum)):
            continue
        seen.add(target.pk)
        provider_counts[edge['provider']] = provider_counts.get(edge['provider'], 0) + 1
        candidates.append((target, edge))
    return candidates


def practice_for_request(request, *, module=None, course_instance=None, token=None):
    """Explicit invalid contexts fail closed; never fall through to course credit."""
    token = token or request.GET.get('recommendation')
    if not token:
        return None
    try:
        item = RecommendationProgress.objects.select_related('activation__enrollment__course_instance__course',
            'activation__enrollment__student', 'module__unit', 'activation__source_module').get(pk=token)
    except (RecommendationProgress.DoesNotExist, ValidationError, ValueError):
        raise PermissionDenied('Invalid recommendation context.')
    if (item.retired_at or not request.user.is_authenticated or item.user_id != request.user.pk or not item.enrollment.active
            or not item.enrollment.course_instance.active
            or (module and item.module_id != module.pk)
            or (course_instance and item.enrollment.course_instance_id != course_instance.pk)
            or not recommendations_enabled(item.enrollment.course_instance)):
        raise PermissionDenied('Recommendation access is unavailable.')
    return item


def proxy_progress(request, params, *, user, module, course_instance):
    token = params.get('recommendation')
    token = token[0] if isinstance(token, list) else token
    if token:
        return practice_for_request(request, token=token, module=module, course_instance=course_instance), False
    return ModuleProgress.get_or_create_progress(user=user, module=module, course_instance=course_instance)


def practice_event(item, event_type, *, source='', payload=None, score=None, progress=None, success=None, event_key=None):
    values = dict(activation=item.activation, recommendation=item, event_type=event_type, source=source,
                  payload=payload or {}, score=score, progress=progress, success=success)
    if event_key:
        return RecommendationEvent.objects.get_or_create(activation=item.activation, event_key=event_key, defaults={k:v for k,v in values.items() if k!='activation'})[0]
    return RecommendationEvent.objects.create(**values)


@transaction.atomic
def apply_practice_snapshot(item, *, source, progress=None, score=None, success=None, is_complete=None, payload=None, event_type=None):
    locked = RecommendationProgress.objects.select_for_update().get(pk=item.pk)
    if locked.retired_at:
        raise PermissionDenied('This recommendation has been retired.')
    attempt = attempt_snapshot(source, payload, score, success, event_type)
    if attempt and attempt['key'] and locked.events.filter(event_key=str(item.pk)+attempt['key'][:60]).exists():
        return item
    new_progress = locked.progress if progress is None else max(0, min(1, float(progress)))
    new_score = locked.score if score is None else max(0, min(100, float(score)))
    complete = bool(is_complete if is_complete is not None else new_progress >= 1)
    first_complete = complete and not locked.is_complete
    locked.progress = max(locked.progress, new_progress)
    locked.score = new_score
    locked.success = bool(success)
    locked.is_complete = locked.is_complete or complete
    if first_complete:
        locked.completed_at = timezone.now()
    locked.state_data = payload
    locked.save()
    practice_event(locked, 'attempt' if attempt else (event_type or 'progress'), source=source, payload=payload,
        score=attempt['score'] if attempt else new_score, progress=new_progress,
        success=attempt['success'] if attempt else success,
        event_key=(str(item.pk)+attempt['key'][:60]) if attempt and attempt['key'] else None)
    if first_complete:
        practice_event(locked, 'completion', source=source, score=new_score, progress=1, success=success)
    item.refresh_from_db()
    return item


def practice_items(enrollment, source_id=None):
    if not recommendations_enabled(enrollment.course_instance):
        return []
    query = RecommendationProgress.objects.filter(activation__enrollment=enrollment, activation__failures__gte=1, activation__activated_at__isnull=False, retired_at__isnull=True).select_related('module', 'activation__source_module')
    if source_id:
        query = query.filter(activation__source_module_id=source_id)
    return [{'id': str(item.pk), 'module_id': item.module_id, 'title': item.module.title,
             'source_id': item.activation.source_module_id, 'source_title': item.activation.source_module.title,
             'provider': item.provider, 'rank': item.rank, 'similarity': item.similarity,
             'progress': item.progress, 'score': item.score, 'is_complete': item.is_complete,
             'feedback': item.feedback, 'attempts': item.attempts,
             'source_url': reverse('courses:launch_iframe_module', args=[enrollment.course_instance_id, item.activation.source_module_id]),
             'url': reverse('courses:recommendation_practice', args=[enrollment.course_instance_id, item.pk]),
             'event_url': reverse('courses:recommendation_event', args=[enrollment.course_instance_id, item.pk])}
            for item in query.order_by('-similarity', 'rank', 'id')]
