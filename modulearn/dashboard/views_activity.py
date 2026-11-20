import json

from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from courses.models import CourseInstance
from . import activity_data as data, activity_exports as exports


def session_for(request, instance_id):
    instance = get_object_or_404(CourseInstance, pk=instance_id)
    # Session ownership, not a global instructor flag or ownership of another session.
    if not (request.user.is_superuser or instance.instructors.filter(pk=request.user.pk).exists()):
        raise PermissionDenied
    return instance


@login_required
@require_GET
@never_cache
def events(request, instance_id):
    instance = session_for(request, instance_id)
    context = request.GET.get('context', 'course')
    try:
        if context not in data.CONTEXTS:
            raise ValidationError('Unknown activity stream.')
        filters = data.filters_from(request.GET)
        if request.GET.get('detail'):
            qs = data.queryset(instance, context)
            record = get_object_or_404(qs, pk=request.GET['detail'])
            return JsonResponse({'payload': record.metadata if context == 'access' else record.payload})
        cursor = request.GET.get('cursor')
        before = None
        if cursor:
            page = signing.loads(cursor, salt='activity-page', max_age=exports.TTL)
            if page['instance'] != instance.pk or page['context'] != context or page['filters'] != filters:
                raise signing.BadSignature
            ceiling, before = page['ceiling'], page['before']
        else:
            ceiling = data.snapshot(instance, context, filters)
        records = data.rows(instance, context, filters, ceiling, before=before, limit=51)
        more = len(records) > 50
        records = records[:50]
        next_cursor = signing.dumps({'instance': instance.pk, 'context': context, 'filters': filters,
                                     'ceiling': ceiling, 'before': records[-1]['id']}, salt='activity-page') if more else None
        result = {'rows': records, 'next': next_cursor}
        if not cursor:
            result['types'] = list(data.queryset(instance, context).order_by('event_type').values_list('event_type', flat=True).distinct())
        return JsonResponse(result)
    except (ValidationError, signing.BadSignature, ValueError, KeyError, OverflowError):
        return JsonResponse({'error': 'Invalid filters or expired page. Refresh the activity list.'}, status=400)


@login_required
@require_POST
@never_cache
def prepare_export(request, instance_id):
    instance = session_for(request, instance_id)
    try:
        body = json.loads(request.body)
        token = body.get('token')
        if not token:
            token = exports.new(instance, request.user, data.filters_from(body), body.get('context', 'course'))
            # Return the durable token before doing work, so a timeout can be retried.
            return JsonResponse({'token': token, 'count': 0, 'done': False})
        path = exports.locate(token, instance, request.user)
        state = exports.advance(path, instance)
        return JsonResponse({'token': token, 'count': state['count'], 'done': state['done'],
                             'download': reverse('dashboard:activity_download', args=[instance.pk]) + '?token=' + token if state['done'] else None})
    except (ValidationError, signing.BadSignature, ValueError, TypeError, AttributeError, OverflowError):
        return JsonResponse({'error': 'Invalid or expired export. Start a new download.'}, status=400)
    except BlockingIOError:
        return JsonResponse({'error': 'Export is already preparing. Retry shortly.'}, status=409)


@login_required
@require_GET
@never_cache
def download(request, instance_id):
    instance = session_for(request, instance_id)
    try:
        path = exports.locate(request.GET.get('token', ''), instance, request.user)
        state = json.loads((path / 'state.json').read_text(encoding='utf-8'))
        if not state['done']:
            return JsonResponse({'error': 'Export is not ready.'}, status=409)
        label = 'all-interactions' if len(state['contexts']) > 1 else state['contexts'][0] + '-activity'
        response = FileResponse((path / 'activity.csv').open('rb'), as_attachment=True,
                                filename=f'{label}-{instance.pk}.csv', content_type='text/csv; charset=utf-8')
        response['X-Content-Type-Options'] = 'nosniff'
        return response
    except signing.BadSignature:
        return JsonResponse({'error': 'Invalid or expired export. Start a new download.'}, status=400)


@login_required
@require_GET
@never_cache
def export_page(request, instance_id):
    instance = session_for(request, instance_id)
    try:
        filters = data.filters_from(request.GET)
    except ValidationError:
        return JsonResponse({'error': 'Invalid export filters.'}, status=400)
    return render(request, 'dashboard/activity_export.html', {'course_instance': instance,
                  'activity_export_options': {**filters, 'context': request.GET.get('context', 'course')}})
