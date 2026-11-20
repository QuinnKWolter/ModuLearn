"""Render unsaved authoring input without creating submissions or course records."""
import json
from django.template.loader import render_to_string
from django.http import JsonResponse


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
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid preview content.'}, status=400)
    return JsonResponse({'html': render_to_string('courses/components/activity_authoring_preview.html', context, request=request)})
