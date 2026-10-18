"""SQL-KnoT's JSON submission and interaction API adapter.

Use the authenticated user and exact placement/session from the proxied page;
the provider's cid is a SQL topic, not a ModuLearn course ID.
"""
import json
import logging
from urllib.parse import urlparse, parse_qs
from django.db import transaction

logger = logging.getLogger(__name__)
HOST = 'adapt2.sis.pitt.edu'


def is_sqlknot_url(url):
    parsed = urlparse(url)
    return parsed.hostname == HOST and parsed.path.startswith('/sqlknot/')


def capture_sqlknot_result(request, host, path, response):
    path = '/' + path.lstrip('/')
    if host != HOST or not path.startswith('/sqlknotserver/') or request.method != 'POST' or response.status_code >= 400:
        return
    if not request.user.is_authenticated:
        return
    from courses.models import Module
    from .tracking_context import enrolled_tracking_session
    from .recommendation_tracking import proxy_progress
    from .progress import apply_progress_snapshot, log_module_progress_event, module_accepts_scored_attempt
    params = parse_qs(urlparse(request.headers.get('Referer', '')).query)
    try:
        module = Module.objects.select_related('unit__course').filter(pk=params.get('module_id', [''])[0]).first()
        if not module or not is_sqlknot_url(module.content_url):
            return
        instance = enrolled_tracking_session(module.unit.course, request.user, params)
        if not instance:
            return
        submitted = json.loads(request.body or '{}')
        result = json.loads(response.content or '{}')
        if not isinstance(submitted, dict):
            return
        # Do not duplicate provider identity/session credentials in research logs.
        submission = {k: submitted[k] for k in ('questionId', 'answer', 'actionType', 'language') if k in submitted}
        payload = {'sqlknot_submission': submission, 'sqlknot_result': result, 'endpoint': path}
        with transaction.atomic():
            progress, _ = proxy_progress(request, params, user=request.user, module=module, course_instance=instance)
            progress = type(progress).objects.select_for_update().get(pk=progress.pk)
            if path != '/sqlknotserver/CheckAnswer':
                log_module_progress_event(progress, event_type='provider_event', source='sqlknot', payload=payload)
                return
            if not isinstance(result, dict) or type(result.get('checkResult')) is not bool:
                return
            if not module_accepts_scored_attempt(progress):
                return
            correct = result['checkResult']
            from courses.models import RecommendationProgress
            if not isinstance(progress, RecommendationProgress):
                log_module_progress_event(progress, source='sqlknot', event_type='attempt',
                    score=100.0 if correct else 0.0, success=correct, payload=payload)
            apply_progress_snapshot(progress, source='sqlknot',
                progress=max(progress.progress or 0, float(correct)),
                score=max(progress.score or 0, 100.0 if correct else 0),
                success=progress.success or correct, is_complete=progress.is_complete or correct,
                payload=payload, event_type='progress')
            # Practice snapshots already maintain their own attempt counter.
            if not isinstance(progress, RecommendationProgress):
                progress.attempts += 1
                progress.save(update_fields=['attempts', 'last_accessed'])
    except (ValueError, TypeError, UnicodeDecodeError):
        logger.warning('SQL-KnoT returned an invalid tracking payload')
