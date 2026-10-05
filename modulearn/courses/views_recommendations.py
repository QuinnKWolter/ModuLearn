import math

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from courses.models import CourseInstance, Enrollment, Module, StaticRecommendationSet
from courses.views import _is_course_instructor, user_can_access_participant_course
from modulearn.learning.services.access_rules import log_module_access
from modulearn.learning.services.course_plugins import is_course_plugin_enabled, normalize_course_plugin_config
from modulearn.learning.services.static_recommendations import parse_uploads, recommendations_for, resolve_nodes


@login_required
@require_http_methods(['GET', 'POST'])
def manage(request, instance_id):
    instance = get_object_or_404(CourseInstance.objects.select_related('course'), pk=instance_id)
    if not _is_course_instructor(request.user, instance):
        raise PermissionDenied
    course = instance.course
    dataset = StaticRecommendationSet.objects.filter(course=course).first()
    if request.method == 'POST':
        try:
            if course.is_locked_for_research and course.instances.filter(
                Q(recruitment_sources__participant_sessions__isnull=False) |
                Q(study__recruitment_sources__participant_sessions__isnull=False)
            ).exists():
                raise ValueError('This course is locked for research. Duplicate it before changing recommendations.')
            action = request.POST.get('action')
            if action == 'upload':
                parsed = parse_uploads(request.FILES.getlist('files'))
                # Parsing and validation finish before the current dataset changes.
                with transaction.atomic():
                    StaticRecommendationSet.objects.update_or_create(course=course, defaults={
                        **parsed, 'bindings': {}, 'options': dataset.options if dataset else {},
                    })
                messages.success(request, 'Recommendation files imported. Review module matches below before enabling the plugin.')
            elif action in {'settings', 'binding'} and dataset:
                with transaction.atomic():
                    dataset = StaticRecommendationSet.objects.select_for_update().get(pk=dataset.pk)
                    if request.POST.get('revision') != dataset.updated_at.isoformat():
                        raise ValueError('These recommendations changed in another window. Reload and try again.')
                    if action == 'binding':
                        key = request.POST.get('node')
                        if key not in dataset.nodes:
                            raise ValueError('Choose an activity from these files.')
                        module_id = int(request.POST.get('module') or 0)
                        if module_id and not course.units.filter(modules__id=module_id).exists():
                            raise ValueError('Choose a module in this course.')
                        dataset.bindings[key] = module_id
                    else:
                        trigger = request.POST.get('trigger', 'completed')
                        if trigger not in {'completed', 'needs_practice'}:
                            raise ValueError('Choose a valid recommendation trigger.')
                        minimum = request.POST.get('minimum_similarity', '').strip()
                        minimum = float(minimum) if minimum else None
                        limit = int(request.POST.get('limit', 9))
                        if minimum is not None and (not math.isfinite(minimum) or not -1 <= minimum <= 1):
                            raise ValueError('Cosine similarity must be between -1 and 1, or blank for no cutoff.')
                        if not 1 <= limit <= 30:
                            raise ValueError('Show between 1 and 30 recommendations.')
                        dataset.options = {'trigger': trigger, 'minimum_similarity': minimum, 'limit': limit}
                        course.plugin_config = normalize_course_plugin_config(course.plugin_config)
                        course.plugin_config['plugins']['static_recommendations']['enabled'] = request.POST.get('enabled') == 'on'
                        course.save(update_fields=['plugin_config'])
                    dataset.save()
                messages.success(request, 'Recommendation settings saved.')
            else:
                raise ValueError('Upload recommendation files first.')
        except (ValueError, TypeError) as exc:
            messages.error(request, str(exc))
        return redirect('courses:static_recommendations', instance_id=instance.pk)
    visualization = None
    if dataset:
        resolved, issues, modules = resolve_nodes(dataset, course)
        if request.GET.get('download') == '1':
            response = JsonResponse({'nodes': dataset.nodes, 'edges': dataset.edges, 'analysis': dataset.analysis,
                                     'provenance': dataset.provenance, 'options': dataset.options, 'bindings': dataset.bindings})
            response['Content-Disposition'] = 'attachment; filename="static-recommendations.json"'
            return response
        linked = [e for e in dataset.edges if e['source'] in resolved and e['target'] in resolved]
        visualization = {
            'nodes': dataset.nodes, 'edges': dataset.edges, 'issues': issues,
            'resolved': {k: {'id': m.pk, 'title': m.title, 'unit': m.unit.title,
                             'preview_url': reverse('courses:preview_iframe_module', args=[m.pk])} for k, m in resolved.items()},
            'code': dataset.analysis.get('code', {}), 'medoids': dataset.analysis.get('medoids', {}),
            'linked_count': len(linked), 'module_count': len(modules),
        }
    else:
        modules = []
    return render(request, 'courses/static_recommendations.html', {
        'course_instance': instance, 'course': course, 'dataset': dataset, 'visualization': visualization,
        'modules': modules, 'enabled': is_course_plugin_enabled(course, 'static_recommendations'),
        'revision': dataset.updated_at.isoformat() if dataset else '',
    })


def _enrollment(request, instance_id):
    instance = get_object_or_404(CourseInstance.objects.select_related('course'), pk=instance_id)
    if getattr(request.user, 'is_anonymous_participant', False) or not user_can_access_participant_course(request.user, instance.pk):
        raise PermissionDenied
    enrollment = Enrollment.objects.filter(student=request.user, course_instance=instance, active=True).first()
    if not enrollment:
        raise PermissionDenied
    return enrollment


@login_required
@require_GET
def queue(request, instance_id):
    enrollment = _enrollment(request, instance_id)
    response = JsonResponse({'enabled': is_course_plugin_enabled(enrollment.course_instance.course, 'static_recommendations'),
                             'items': recommendations_for(enrollment)})
    response['Cache-Control'] = 'no-store'
    return response


@login_required
@require_GET
def launch(request, instance_id, module_id):
    enrollment = _enrollment(request, instance_id)
    item = next((r for r in recommendations_for(enrollment) if r['module_id'] == module_id), None)
    if not item:
        messages.info(request, 'Your recommendations have changed. Choose another activity from the course page.')
        return redirect('courses:course_detail', instance_id=instance_id)
    module = get_object_or_404(Module, pk=module_id, unit__course=enrollment.course_instance.course)
    log_module_access(request.user, module, enrollment.course_instance, event_type='view',
                      metadata={'source': 'static_recommendations', 'query_module_id': item['source_id'],
                                'similarity': item['similarity'], 'rank': item['rank']})
    return redirect('courses:launch_iframe_module', instance_id=instance_id, module_id=module_id)
