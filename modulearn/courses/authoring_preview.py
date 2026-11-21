"""Render unsaved authoring input without creating submissions or course records."""
import json
import uuid
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import URLValidator
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET
from django.template.loader import render_to_string
from django.http import JsonResponse
from .models import Module


def owned_module(request, module_id):
    module = get_object_or_404(Module.objects.select_related('unit__course'), pk=module_id)
    if not (request.user.is_staff or module.unit.course.instructors.filter(pk=request.user.pk).exists()
            or module.unit.course.instances.filter(instructors=request.user).exists()):
        raise PermissionDenied('Activity author access required.')
    return module


@login_required
@require_GET
def launch_authoring_preview(request):
    try:
        data = signing.loads(request.GET.get('token', ''), salt='activity-authoring-preview', max_age=3600)
        if data['user_id'] != request.user.pk or not (request.user.is_instructor or request.user.is_staff):
            raise PermissionDenied('Preview belongs to another instructor.')
        module = owned_module(request, data['module_id']) if data['module_id'] else Module()
        module.content_url = data['content_url']
        module.provider_id = data['provider_id']
        module.supported_protocols = data['protocols']
        module.title = data['title']
    except (signing.BadSignature, KeyError, TypeError):
        return HttpResponseBadRequest('Preview expired. Close it and open Activity Preview again.')
    from .views import render_instructor_activity_preview
    response = render_instructor_activity_preview(request, module)
    response['Cache-Control'] = 'private, no-store'
    response['Referrer-Policy'] = 'same-origin'
    return response


def activity_preview_response(request, raw):
    if len(raw) > 250000:
        return JsonResponse({'error': 'Preview is too large.'}, status=400)
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError

        def text(obj, key, limit=50000):
            value = obj.get(key, '')
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError
            return value

        questions = data.get('questions', [])
        if not isinstance(questions, list) or len(questions) > 200:
            raise ValueError
        normalized = []
        for index, question in enumerate(questions):
            if not isinstance(question, dict):
                raise ValueError
            kind = text(question, 'type', 32)
            if kind not in {'short_answer', 'long_answer', 'single_choice', 'multiple_choice', 'likert'}:
                raise ValueError
            options = question.get('options', [])
            if not isinstance(options, list) or len(options) > 200 or any(not isinstance(x, str) or len(x) > 5000 for x in options):
                raise ValueError
            normalized.append({
                'id': f'author_preview_{index}', 'prompt': text(question, 'prompt'),
                'help_text': text(question, 'help'), 'question_type': kind,
                'required': question.get('required') is True, 'options': options,
                'likert_min_label': text(question, 'low', 255),
                'likert_max_label': text(question, 'high', 255),
            })
        context = {
            'module': {'title': text(data, 'title', 500), 'description': text(data, 'description')},
            'module_form': {'instructions': text(data, 'instructions'), 'submit_button_label': text(data, 'continuation', 64)},
            'questions': normalized, 'preview_only': True, 'participant_mode': True,
            'is_form': data.get('isForm') is True,
        }
        if not context['is_form']:
            module_id = data.get('moduleId')
            module = owned_module(request, module_id) if module_id else None
            kind = text(data, 'activityType', 40)
            if kind == Module.MODULE_TYPE_FILE:
                context['file_url'] = module.content_file.url if module and module.content_file else ''
            else:
                url = text(data, 'contentUrl', 4000).strip()
                if url:
                    URLValidator(schemes=['https', 'http'])(url)
                    provider = text(data, 'providerId', 255)
                    raw_protocols = text(data, 'protocols', 255)
                    protocols = [item.strip() for item in raw_protocols.split(',') if item.strip()]
                    candidate = Module(content_url=url, provider_id=provider, supported_protocols=protocols)
                    is_lti = candidate.select_launch_protocol() == 'lti' or '/lti/' in url
                    if is_lti and (not module or (url, provider, protocols) !=
                            (module.content_url, module.provider_id, module.supported_protocols)):
                        context['launch_notice'] = 'Save this LTI activity before previewing its signed launch.'
                    else:
                        token = signing.dumps({'user_id': request.user.pk, 'module_id': module.pk if module else None,
                            'content_url': url, 'provider_id': provider, 'protocols': protocols,
                            'title': context['module']['title'], 'nonce': uuid.uuid4().hex},
                            salt='activity-authoring-preview', compress=True)
                        context['preview_launch_url'] = reverse('courses:authoring_preview_launch') + '?token=' + token
    except (TypeError, ValueError, ValidationError):
        return JsonResponse({'error': 'Invalid preview content.'}, status=400)
    return JsonResponse({'html': render_to_string('courses/components/activity_authoring_preview.html', context, request=request)})
