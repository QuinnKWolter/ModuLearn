"""DBQA's query-step logs and fractional LTI result submissions."""
import math
from django.db import transaction


def capture_dbqa_result(request, host, path, response):
    path = '/' + path.lstrip('/')
    if host != 'codesmell.org' or path not in {'/dbqa/query/log', '/dbqa/lti/1.1/result/send'} or request.method != 'POST':
        return
    if not request.user.is_authenticated:
        return
    from lti.models import LTILaunchCache
    from courses.models import Module, ModuleProgress
    from .tracking_context import enrolled_tracking_session
    from .progress import log_module_progress_event, apply_progress_snapshot
    launch = LTILaunchCache.objects.filter(source_id=request.POST.get('sourcedid'), user_id=request.user.pk,
        tool__in=['dbqa', 'paws_dbqa']).first()
    if not launch or launch.is_expired():
        return
    module = Module.objects.select_related('unit__course').filter(pk=launch.module_id).first()
    if not module:
        return
    instance = enrolled_tracking_session(module.unit.course, request.user, {'course_instance_id': str(launch.course_instance_id)})
    if not instance:
        return
    payload = {key: request.POST[key] for key in ('query', 'currentStep', 'totalSteps', 'interactionType', 'stepExplanation', 'score') if key in request.POST}
    payload['upstream_status'] = response.status_code
    with transaction.atomic():
        progress, _ = ModuleProgress.get_or_create_progress(user=request.user, module=module, course_instance=instance)
        progress = ModuleProgress.objects.select_for_update().get(pk=progress.pk)
        log_module_progress_event(progress, event_type='provider_event', source='dbqa', payload=payload)
        if path != '/dbqa/lti/1.1/result/send' or response.status_code >= 400:
            return
        try:
            score = float(request.POST.get('score', ''))
        except (TypeError, ValueError):
            return
        if not math.isfinite(score) or not 0 <= score <= 1:
            return
        apply_progress_snapshot(progress, source='dbqa', progress=max(progress.progress or 0, score),
            score=max(progress.score or 0, score * 100), success=progress.success or score == 1,
            is_complete=progress.is_complete or score == 1, payload=payload, event_type='progress')
