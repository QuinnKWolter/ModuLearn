import math

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import URLValidator
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
                uploads = request.FILES.getlist('files')
                if len(uploads) == 1 and uploads[0].name.lower().endswith('.json'):
                    from modulearn.learning.services.recommendation_package import install_package
                    from main.templatetags.ui_i18n import ui
                    report = install_package(course.pk, uploads[0].read(10 * 1024 * 1024 + 1), actor=request.user)
                    messages.success(request, ui('Recommendations ready: {activities} activities, {links} links. Created {created} activities; updated {updated} active assignments. The plugin is enabled.',
                        activities=report['activities'], links=report['links'], created=len(report['created_modules']), updated=report['assignments_changed']))
                    return redirect('courses:static_recommendations', instance_id=instance.pk)
                parsed = parse_uploads(request.FILES.getlist('files'))
                # Parsing and validation finish before the current dataset changes.
                with transaction.atomic():
                    StaticRecommendationSet.objects.update_or_create(course=course, defaults={
                        **parsed, 'bindings': {}, 'options': dataset.options if dataset else {},
                    })
                messages.success(request, 'Recommendation files imported. Review module matches below before enabling the plugin.')
            elif action in {'settings', 'binding', 'practice'} and dataset:
                with transaction.atomic():
                    dataset = StaticRecommendationSet.objects.select_for_update().get(pk=dataset.pk)
                    if request.POST.get('revision') != dataset.updated_at.isoformat():
                        raise ValueError('These recommendations changed in another window. Reload and try again.')
                    if action == 'practice':
                        module = get_object_or_404(Module, pk=request.POST.get('module'), unit__course=course, is_recommendation_only=True)
                        url = request.POST.get('content_url', '').strip()
                        URLValidator(schemes=['https', 'http'])(url)
                        module.content_url = url
                        module.is_visible = request.POST.get('visible') == 'on'
                        module.save(update_fields=['content_url', 'is_visible'])
                    elif action == 'binding':
                        key = request.POST.get('node')
                        if key not in dataset.nodes:
                            raise ValueError('Choose an activity from these files.')
                        module_id = int(request.POST.get('module') or 0)
                        url = request.POST.get('new_content_url', '').strip()
                        if url:
                            if module_id:
                                raise ValueError('Choose an existing activity or provide a new URL, not both.')
                            if any(edge['source'] == key for edge in dataset.edges):
                                raise ValueError('Add original problems to the course outline. Only recommendation targets belong in the practice library.')
                            URLValidator(schemes=['https', 'http'])(url)
                            unit = course.units.order_by('order', 'id').first()
                            if not unit:
                                raise ValueError('Add a course unit before adding practice activities.')
                            node = dataset.nodes[key]
                            module = Module.objects.create(unit=unit, title=node['title'], content_url=url,
                                provider_id=node['provider'], module_type=Module.MODULE_TYPE_SPLICE_SMART_CONTENT,
                                supported_protocols=['splice'], is_recommendation_only=True)
                            module_id = module.pk
                        if module_id and not course.units.filter(modules__id=module_id).exists():
                            raise ValueError('Choose a module in this course.')
                        dataset.bindings[key] = module_id
                    else:
                        trigger = request.POST.get('trigger', 'needs_practice')
                        if trigger not in {'completed', 'needs_practice'}:
                            raise ValueError('Choose a valid recommendation trigger.')
                        minimum = request.POST.get('minimum_similarity', '').strip()
                        minimum = float(minimum) if minimum else None
                        if any(p.get('ranking') == 'explicit_rank' for p in dataset.provenance):
                            minimum = None
                        limit = int(request.POST.get('limit', 2))
                        threshold = int(request.POST.get('failure_threshold', 1))
                        if not 1 <= threshold <= 100:
                            raise ValueError('Choose between 1 and 100 unsuccessful attempts.')
                        if minimum is not None and (not math.isfinite(minimum) or not -1 <= minimum <= 1):
                            raise ValueError('Cosine similarity must be between -1 and 1, or blank for no cutoff.')
                        if not 1 <= limit <= 30:
                            raise ValueError('Show between 1 and 30 recommendations per activity type.')
                        dataset.options = {'trigger': 'needs_practice', 'minimum_similarity': minimum, 'limit': limit, 'failure_threshold': threshold}
                        course.plugin_config = normalize_course_plugin_config(course.plugin_config)
                        course.plugin_config['plugins']['static_recommendations']['enabled'] = request.POST.get('enabled') == 'on'
                        course.save(update_fields=['plugin_config'])
                    dataset.save()
                messages.success(request, 'Recommendation settings saved.')
            else:
                raise ValueError('Upload recommendation files first.')
        except (ValueError, TypeError, ValidationError) as exc:
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
        'practice_modules': [m for m in modules if m.is_recommendation_only],
        'revision': dataset.updated_at.isoformat() if dataset else '',
    })


def _enrollment(request, instance_id):
    instance = get_object_or_404(CourseInstance.objects.select_related('course'), pk=instance_id)
    if not user_can_access_participant_course(request.user, instance.pk):
        raise PermissionDenied
    enrollment = Enrollment.objects.filter(student=request.user, course_instance=instance, active=True).first()
    if not enrollment:
        raise PermissionDenied
    return enrollment


@login_required
@require_GET
def queue(request, instance_id):
    enrollment = _enrollment(request, instance_id)
    from modulearn.learning.services.recommendation_tracking import practice_items
    source = request.GET.get('source')
    if source and not source.isdecimal():
        return JsonResponse({'error': 'Invalid source module.'}, status=400)
    response = JsonResponse({'enabled': is_course_plugin_enabled(enrollment.course_instance.course, 'static_recommendations'),
                             'items': practice_items(enrollment, source)})
    response['Cache-Control'] = 'no-store'
    return response


@login_required
@require_GET
def launch(request, instance_id, module_id):
    enrollment = _enrollment(request, instance_id)
    # Old links must never launch a credit-bearing module as recommendation practice.
    return redirect('courses:course_detail', instance_id=instance_id)


def _practice(request, instance_id, recommendation_id):
    from modulearn.learning.services.recommendation_tracking import practice_for_request
    enrollment = _enrollment(request, instance_id)
    return practice_for_request(request, token=str(recommendation_id), course_instance=enrollment.course_instance)


@login_required
@require_GET
def practice(request, instance_id, recommendation_id):
    from courses.views import launch_iframe_module
    item = _practice(request, instance_id, recommendation_id)
    # Reuse the provider launch normalization, with an explicit isolated context.
    request.GET = request.GET.copy()
    request.GET['recommendation'] = str(item.pk)
    return launch_iframe_module(request, instance_id, item.module_id)


@login_required
@require_http_methods(['POST'])
def practice_progress(request, instance_id, recommendation_id):
    import json
    from modulearn.learning.services.progress import record_module_session_event
    item = _practice(request, instance_id, recommendation_id)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError('Invalid payload.')
        if 'provider_event' in data:
            from modulearn.learning.services.cupcake_tracking import record_cupcake_event
            record_cupcake_event(item, data['provider_event'])
        elif 'event_type' in data:
            record_module_session_event(item, event_type=data['event_type'], payload=data.get('payload', {}))
        else:
            activity = data['data'][0]
            for key in ('score', 'progress'):
                if key in activity and not math.isfinite(float(activity[key])):
                    raise ValueError('Scores must be finite.')
            item.update_from_activity_attempt(data)
    except (ValueError, TypeError, KeyError, IndexError):
        return JsonResponse({'error': 'Invalid activity event.'}, status=400)
    return JsonResponse({'success': True, 'module_progress': {'score': item.score, 'progress': item.progress, 'is_complete': item.is_complete}})


@login_required
@require_http_methods(['POST'])
def practice_event_view(request, instance_id, recommendation_id):
    import json
    from django.utils import timezone
    from modulearn.learning.services.recommendation_tracking import practice_event
    item = _practice(request, instance_id, recommendation_id)
    try:
        data = json.loads(request.body)
        event = data['event_type']
        if event not in {'impression', 'visit', 'return_to_problem', 'sidebar_open', 'sidebar_close', 'feedback_shown', 'feedback'}:
            raise ValueError
        value = data.get('value', '')
        if event.startswith('feedback') and not item.is_complete:
            raise ValueError
        if event == 'feedback' and value not in {'up', 'down', 'skipped'}:
            raise ValueError
        with transaction.atomic():
            from courses.models import RecommendationProgress
            from django.db.models import F
            # Acquire the write lock before reading (also safe on SQLite, which
            # cannot upgrade two simultaneous deferred read transactions).
            RecommendationProgress.objects.filter(pk=item.pk).update(last_accessed=F('last_accessed'))
            item = RecommendationProgress.objects.select_for_update().get(pk=item.pk)
            if item.retired_at:
                raise PermissionDenied('This recommendation has been retired.')
            if event == 'feedback':
                item.feedback = value
                item.save(update_fields=['feedback'])
            if event == 'feedback_shown':
                if item.feedback_prompted_at:
                    return JsonResponse({'success': True})
                item.feedback_prompted_at = timezone.now()
                item.save(update_fields=['feedback_prompted_at'])
            client_id = str(data.get('event_id', ''))[:48]
            practice_event(item, event, source='sidebar', payload={'value': value},
                           event_key=(str(item.pk)+client_id) if client_id else None)
    except (ValueError, TypeError, KeyError):
        return JsonResponse({'error': 'Invalid recommendation event.'}, status=400)
    return JsonResponse({'success': True})


@login_required
@require_GET
def research_logs(request, instance_id):
    import csv
    import io
    import json
    from django.core.paginator import Paginator
    from django.db.models import Count
    from django.http import StreamingHttpResponse
    from courses.models import RecommendationEvent, RecommendationProgress, ModuleProgressEvent
    def rank_method(activation):
        return 'explicit_rank' if any(p.get('ranking') == 'explicit_rank' for p in activation.configuration.get('provenance', [])) else 'cosine_similarity'
    instance = get_object_or_404(CourseInstance.objects.select_related('course'), pk=instance_id)
    if not _is_course_instructor(request.user, instance):
        raise PermissionDenied
    events = RecommendationEvent.objects.filter(activation__enrollment__course_instance=instance).select_related(
        'activation__enrollment__student', 'activation__source_module', 'recommendation__module')
    query = request.GET.get('q', '').strip()
    kind = request.GET.get('event', '').strip()
    course_events = ModuleProgressEvent.objects.filter(module_progress__enrollment__course_instance=instance).select_related(
        'user', 'module', 'module_progress__enrollment').order_by('-created_at', '-id')
    if query:
        course_events = course_events.filter(Q(user__username__icontains=query) | Q(module__title__icontains=query))
    if kind:
        course_events = course_events.filter(event_type=kind)
    if request.GET.get('download') == 'course_csv':
        def course_rows():
            stream = io.StringIO(); writer = csv.writer(stream)
            writer.writerow(['context', 'event_id', 'time_utc', 'student', 'enrollment_id', 'module_id', 'activity',
                             'event', 'source', 'attempt_score', 'progress', 'success', 'payload'])
            yield stream.getvalue()
            for event in course_events.iterator(chunk_size=500):
                values = ['course', event.pk, event.created_at.isoformat(), event.user.username,
                    event.module_progress.enrollment_id, event.module_id, event.module.title, event.event_type,
                    event.source, event.score, event.progress, event.success, json.dumps(event.payload, ensure_ascii=False)]
                values = ["'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v for v in values]
                stream.seek(0); stream.truncate(0); writer.writerow(values); yield stream.getvalue()
        response = StreamingHttpResponse(course_rows(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="course-activity-{instance.pk}.csv"'
        return response
    if query:
        events = events.filter(Q(activation__enrollment__student__username__icontains=query) |
            Q(activation__source_module__title__icontains=query) | Q(recommendation__module__title__icontains=query))
    if kind:
        events = events.filter(event_type=kind)
    assignments = RecommendationProgress.objects.filter(activation__enrollment__course_instance=instance).select_related(
        'activation__source_module', 'activation__enrollment__student', 'module').annotate(
        visits=Count('events', filter=Q(events__event_type='visit')),
        impressions=Count('events', filter=Q(events__event_type='impression')),
        submissions=Count('events', filter=Q(events__event_type='attempt'))).order_by('-activation__activated_at', 'id')
    if query:
        assignments = assignments.filter(Q(activation__enrollment__student__username__icontains=query) |
            Q(activation__source_module__title__icontains=query) | Q(module__title__icontains=query))
    if request.GET.get('download') == 'summary':
        def summary_rows():
            stream=io.StringIO(); writer=csv.writer(stream)
            writer.writerow(['recommendation_id','enrollment_id','student','original_problem','recommended_activity',
                'provider','rank','similarity','activated_at','impressions','visits','submissions','score','progress','completed_at','feedback','retired_at','ranking_method'])
            yield stream.getvalue()
            for item in assignments.iterator(chunk_size=500):
                values=[str(item.pk),item.activation.enrollment_id,item.activation.enrollment.student.username,
                    item.activation.source_module.title,item.module.title,item.provider,item.rank,item.similarity if rank_method(item.activation) != 'explicit_rank' else '',
                    item.activation.activated_at.isoformat() if item.activation.activated_at else '',item.impressions,item.visits,
                    item.submissions,item.score,item.progress,item.completed_at.isoformat() if item.completed_at else '',item.feedback,
                    item.retired_at.isoformat() if item.retired_at else '', rank_method(item.activation)]
                values=["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v for v in values]
                stream.seek(0);stream.truncate(0);writer.writerow(values);yield stream.getvalue()
        response=StreamingHttpResponse(summary_rows(),content_type='text/csv; charset=utf-8')
        response['Content-Disposition']=f'attachment; filename="recommendation-summary-{instance.pk}.csv"'
        return response
    if request.GET.get('download') == 'csv':
        def rows():
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(['event_id', 'time_utc', 'student', 'enrollment_id', 'source_module_id', 'original_problem',
                'recommendation_id', 'target_module_id', 'recommended_activity', 'provider', 'rank', 'similarity',
                'event', 'source', 'attempt_score', 'progress', 'success', 'payload', 'ranking_method'])
            yield stream.getvalue()
            for event in events.iterator(chunk_size=500):
                item = event.recommendation
                values = [event.pk, event.created_at.isoformat(), event.activation.enrollment.student.username,
                    event.activation.enrollment_id, event.activation.source_module_id, event.activation.source_module.title,
                    item.pk if item else '', item.module_id if item else '', item.module.title if item else '',
                    item.provider if item else '', item.rank if item else '', item.similarity if item and rank_method(event.activation) != 'explicit_rank' else '',
                    event.event_type, event.source, event.score, event.progress, event.success, json.dumps(event.payload, ensure_ascii=False), rank_method(event.activation)]
                # Prevent spreadsheet formula execution when instructors open exports.
                values = ["'"+v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v for v in values]
                stream.seek(0); stream.truncate(0); writer.writerow(values)
                yield stream.getvalue()
        response = StreamingHttpResponse(rows(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="recommendation-events-{instance.pk}.csv"'
        return response
    params = request.GET.copy(); params.pop('page', None); params.pop('assignments_page', None); params.pop('course_page', None); params.pop('download', None)
    items = RecommendationProgress.objects.filter(activation__enrollment__course_instance=instance)
    return render(request, 'courses/recommendation_logs.html', {'course_instance': instance,
        'page': Paginator(events, 50).get_page(request.GET.get('page')), 'filters': params.urlencode(),
        'course_page': Paginator(course_events, 50).get_page(request.GET.get('course_page')),
        'assignment_page': Paginator(assignments, 25).get_page(request.GET.get('assignments_page')),
        'q': query, 'kind': kind, 'event_types': ['activated', 'source_attempt', 'impression', 'visit', 'launch', 'attempt',
        'completion', 'return_to_problem', 'sidebar_open', 'sidebar_close', 'feedback_shown', 'feedback', 'tab_focus', 'tab_blur', 'iframe_load', 'dataset_transition', 'provider_event'],
        'assigned': items.count(), 'completed': items.filter(is_complete=True).count(),
        'rated': items.filter(feedback__in=['up', 'down']).count()})
