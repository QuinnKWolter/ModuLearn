"""Read-only, session-scoped integration evidence. Never synthesizes grades."""
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from courses.models import CourseInstance, Module, ModuleProgress, ModuleProgressEvent
from lti.models import LTILaunchCache, LTIOutcomeLog


def integration_evidence(instance, user):
    """Only the requesting instructor's test evidence, never student analytics."""
    modules = list(Module.objects.filter(unit__course=instance.course).order_by('unit__order', 'order', 'pk'))
    progress = list(ModuleProgress.objects.filter(enrollment__course_instance=instance, user=user))
    counts = defaultdict(dict)
    for row in ModuleProgressEvent.objects.filter(module_progress__in=progress).values(
            'module_progress_id', 'event_type').annotate(total=Count('pk')):
        counts[row['module_progress_id']][row['event_type']] = row['total']
    by_module = {p.module_id: p for p in progress}
    launches = LTILaunchCache.objects.filter(course_instance_id=instance.pk, user_id=user.pk)
    launch_counts = dict(launches.values('module_id').annotate(total=Count('pk')).values_list('module_id', 'total'))
    source_modules = dict(launches.values_list('source_id', 'module_id'))
    outcomes = defaultdict(list)
    # Allowlisted fields only: no tokens, OAuth parameters, URLs, error payloads or secrets.
    for outcome in LTIOutcomeLog.objects.filter(source_id__in=launches.values('source_id')).order_by('-received_at'):
        outcomes[source_modules[outcome.source_id]].append({
            'received_at': outcome.received_at.isoformat(), 'success': outcome.success,
            'score': outcome.score_normalized,
        })
    rows = []
    for module in modules:
        p = by_module.get(module.pk)
        rows.append({'module_id': module.pk, 'title': module.title,
                     'provider': module.platform_name or module.provider_id,
                     'protocol': module.select_launch_protocol(),
                     'content_type': (module.content_data or {}).get('validation', {}).get('catalog_type', ''),
                     'launch_url': reverse('courses:launch_iframe_module', args=[instance.pk, module.pk]),
                     'score': p.score if p else None, 'complete': p.is_complete if p else False,
                     'progress': round(p.progress * 100, 2) if p else 0, 'attempts': p.attempts if p else 0,
                     'event_counts': counts[p.pk] if p else {},
                     'lti_launches': launch_counts.get(module.pk, 0), 'outcomes': outcomes[module.pk]})
    return {'generated_at': timezone.now().isoformat(), 'instance_id': instance.pk, 'modules': rows}


@login_required
@require_GET
def integration_testing(request, instance_id):
    from courses.views import _is_course_instructor
    instance = get_object_or_404(CourseInstance.objects.select_related('course'), pk=instance_id)
    if not _is_course_instructor(request.user, instance):
        raise PermissionDenied
    report = integration_evidence(instance, request.user)
    report['callback_url'] = request.build_absolute_uri(reverse('lti_outcome'))
    if request.GET.get('format') == 'json':
        response = JsonResponse(report, json_dumps_params={'indent': 2})
        response['Content-Disposition'] = f'attachment; filename="integration-session-{instance.pk}.json"'
    else:
        response = render(request, 'courses/integration_testing.html', {'instance': instance, 'report': report})
    response['Cache-Control'] = 'private, no-store'
    return response
