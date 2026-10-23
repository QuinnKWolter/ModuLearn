import json
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods
from .models import CourseInstance
from .views import _is_course_instructor
from modulearn.learning.services.grading import normalize_policy, session_results, refresh_session_grades


def check_structure_edit(course):
    if course.is_locked_for_research and course.instances.filter(
        Q(recruitment_sources__participant_sessions__isnull=False) |
        Q(study__recruitment_sources__participant_sessions__isnull=False)
    ).exists():
        raise PermissionDenied('Research protocol is locked after recruitment starts.')


@login_required
@require_http_methods(['GET', 'POST'])
def grading(request, instance_id):
    instance = get_object_or_404(CourseInstance.objects.select_related('course'), pk=instance_id)
    if not _is_course_instructor(request.user, instance):
        raise PermissionDenied
    units = list(instance.course.units.annotate(graded_count=Count('modules', filter=Q(
        is_visible=True, modules__is_visible=True, modules__is_graded=True, modules__is_recommendation_only=False))))
    from modulearn.learning.services.grading import eligible_modules, graded_module_ids
    from collections import Counter
    modules = list(eligible_modules(instance.course))
    selected = graded_module_ids(modules)
    counts = Counter(m.unit_id for m in modules if m.id in selected)
    for unit in units:
        unit.graded_count = counts[unit.id]
    if request.method == 'GET':
        # Removed units must not strand the configuration page with stale IDs.
        valid_ids = {str(unit.id) for unit in units}
        policy = dict(instance.grading_policy)
        policy['units'] = {key: value for key, value in policy.get('units', {}).items() if key in valid_ids}
        policy['groups'] = [dict(group, unit_ids=[id for id in group['unit_ids'] if id in valid_ids])
                            for group in policy.get('groups', []) if any(id in valid_ids for id in group['unit_ids'])]
        return render(request, 'courses/grading.html', {
            'course_instance': instance, 'units': units,
            'policy': normalize_policy(policy, [u.id for u in units]),
        })
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError('Invalid request.')
        policy = normalize_policy(data.get('policy'), [u.id for u in units])
        if data.get('save') is True:
            check_structure_edit(instance.course)
            with transaction.atomic():
                instance.grading_policy = policy
                instance.save(update_fields=['grading_policy'])
                refresh_session_grades(instance)
        return JsonResponse({'rows': session_results(instance, policy), 'saved': data.get('save') is True})
    except (ValueError, TypeError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)
