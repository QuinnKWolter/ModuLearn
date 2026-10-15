"""Capture QuizJET's server-graded form responses through the existing proxy."""
import re
from html import escape
from urllib.parse import parse_qs, urlparse

from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden

from courses.models import CourseInstance, Enrollment, Module, ModuleProgress
from .recommendation_tracking import practice_for_request
from .progress import apply_progress_snapshot, module_accepts_scored_attempt

HOSTS = {'pawscomp2.sis.pitt.edu', 'adapt2.sis.pitt.edu'}
CONTEXT_KEYS = ('module_id', 'course_instance_id', 'recommendation')


def is_quizjet_url(url):
    parsed = urlparse(url or '')
    return parsed.hostname in HOSTS and parsed.path.startswith('/quizjet/')


def process_quizjet_response(request, host, path, response):
    if host not in HOSTS or not path.startswith('quizjet/') or response.status_code >= 400:
        return response
    if 'text/html' not in response.get('Content-Type', ''):
        return response
    params = parse_qs(urlparse(request.META.get('HTTP_REFERER', '')).query)
    for mapping in (request.GET, request.POST):
        for key in CONTEXT_KEYS:
            if mapping.get(key):
                params[key] = [mapping[key]]
    context = {key: params[key][0] for key in CONTEXT_KEYS if params.get(key)}
    if not context.get('module_id') or not context.get('course_instance_id'):
        return response
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return HttpResponseForbidden('Sign in to record this activity.')
    try:
        instance = CourseInstance.objects.filter(pk=context['course_instance_id']).first()
        module = Module.objects.filter(pk=context['module_id'], unit__course_id=instance.course_id).first() if instance else None
    except (ValueError, TypeError):
        return HttpResponseForbidden('Invalid activity context.')
    instructor_preview = bool(instance and instance.instructors.filter(pk=request.user.pk).exists())
    enrollment = Enrollment.objects.filter(student=request.user, active=True,
        course_instance=instance).first() if instance else None
    if not module or not (enrollment or instructor_preview):
        return HttpResponseForbidden('Activity enrollment not found.')
    try:
        practice = practice_for_request(request, token=context.get('recommendation'), module=module, course_instance=instance)
    except PermissionDenied:
        return HttpResponseForbidden('Invalid recommendation context.')
    html = response.content.decode('utf-8', errors='replace')
    # Only the submitted answer's response is a scored attempt; reloads and
    # "Try Again" requests do not increment the counter.
    correct = bool(re.search(r'>\s*(?:CORRECT|Correct)\s*!\s*<', html))
    wrong = bool(re.search(r'>\s*(?:WRONG|Wrong)\s*!\s*<', html))
    if (practice or not instructor_preview) and request.method == 'POST' and request.POST.get('inputans') is not None and (correct or wrong):
        if practice:
            progress = practice
        else:
            progress, _ = ModuleProgress.get_or_create_progress(user=request.user, module=module, course_instance=enrollment.course_instance)
        if module_accepts_scored_attempt(progress):
            apply_progress_snapshot(progress, source='quizjet', score=100 if correct else 0,
                progress=1 if correct else progress.progress, is_complete=progress.is_complete or correct,
                success=correct, event_type='outcome',
                payload={'answer': request.POST.get('inputans'), 'code': request.POST.get('code', ''),
                         'rdfID': request.POST.get('rdfID', ''), 'correct': correct})
            progress.attempts += 1
            progress.save(update_fields=['attempts', 'last_accessed'])
    fields = ''.join(f'<input type="hidden" name="{key}" value="{escape(value, quote=True)}">' for key,value in context.items())
    html = re.sub(r'(<form\b[^>]*>)', lambda match: match[1]+fields, html, flags=re.I)
    response.content = html.encode('utf-8')
    if response.has_header('Content-Length'):
        response['Content-Length'] = str(len(response.content))
    return response
