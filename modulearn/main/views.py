from django.shortcuts import render

from recruitment.services.participants import participant_course_redirect
from modulearn.core.roles import get_user_role_snapshot


def home(request, audience=None):
    redirect_response = participant_course_redirect(getattr(request, "user", None))
    if redirect_response:
        return redirect_response
    # Account roles determine the landing view, including legacy audience URLs.
    # Saved audience preferences must not override the signed-in user's role.
    role = get_user_role_snapshot(request.user)
    audience = 'teachers' if role['effective_is_instructor'] else 'students' if role['effective_is_student'] else 'overview'
    return render(request, 'main/home.html', {'home_audience': audience})


def info(request):
    return render(request, 'main/info.html')


def about(request):
    return info(request)


def contact(request):
    return info(request)


from django.views.decorators.http import require_POST


@require_POST
def report_translation(request):
    import hashlib
    import json
    from urllib.parse import urlsplit
    from django.conf import settings
    from django.core.cache import cache
    from django.http import JsonResponse
    from .models import TranslationReport

    if len(request.body) > 16384:
        return JsonResponse({'error': 'The report is too long.'}, status=400)
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid report.'}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({'error': 'Invalid report.'}, status=400)
    fields = {key: data.get(key, '') for key in ('language', 'page_path', 'original_text', 'suggestion')}
    if not all(isinstance(value, str) for value in fields.values()):
        return JsonResponse({'error': 'Invalid report.'}, status=400)
    if fields['language'] not in dict(settings.LANGUAGES) or not fields['original_text'].strip():
        return JsonResponse({'error': 'Enter the text you want to report.'}, status=400)
    if any(len(fields[k]) > limit for k, limit in [('page_path',500),('original_text',1000),('suggestion',2000)]):
        return JsonResponse({'error': 'The report is too long.'}, status=400)
    try:
        parsed = urlsplit(fields['page_path'])
    except ValueError:
        return JsonResponse({'error': 'Invalid page path.'}, status=400)
    path = parsed.path
    if parsed.scheme or parsed.netloc or not path.startswith('/') or path.startswith('//'):
        return JsonResponse({'error': 'Invalid page path.'}, status=400)
    # Retain no IP address. The short-lived cache key limits anonymous spam too.
    identity = 'user:' + str(request.user.pk) if request.user.is_authenticated else 'ip:' + request.META.get('REMOTE_ADDR', '')
    key = 'translation-report:' + hashlib.sha256((settings.SECRET_KEY + identity).encode()).hexdigest()
    cache.add(key, 0, 3600)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, 3600); count = 1
    if count > 10:
        return JsonResponse({'error': 'Too many reports. Please try again later.'}, status=429)
    TranslationReport.objects.create(reporter=request.user if request.user.is_authenticated else None,
        language=fields['language'], page_path=path, original_text=fields['original_text'].strip(),
        suggestion=fields['suggestion'].strip())
    return JsonResponse({'message': 'Thank you. Your report has been sent.'}, status=201)
