"""Capture QuizJET's server-graded form responses through the existing proxy."""
import re
from html import escape
from html.parser import HTMLParser
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
    return parsed.hostname in HOSTS and parsed.path.startswith(('/quizjet/', '/quizpet/'))


def _assessment_result(html):
    """QuizJET svc=pretest suppresses text feedback but emits its graded outcome."""
    class OutcomeFrames(HTMLParser):
        def __init__(self):
            super().__init__()
            self.values = set()
        def handle_starttag(self, tag, attrs):
            if tag.lower() != 'iframe':
                return
            src = dict(attrs).get('src', '')
            parsed = urlparse(src)
            # Only accept the known provider notification, never arbitrary param=1 text.
            if parsed.hostname and parsed.hostname not in HOSTS:
                return
            known_path = parsed.path == '/um-vis-notificator/remote_update.html' or any(
                parsed.path == f'/proxy/{scheme}/{host}/um-vis-notificator/remote_update.html'
                for host in HOSTS for scheme in ('http', 'https'))
            # FORCE_SCRIPT_NAME can prefix rewritten local proxy paths.
            if not known_path:
                known_path = bool(re.fullmatch(r'/modulearn/proxy/https?/(?:adapt2|pawscomp2)\.sis\.pitt\.edu/um-vis-notificator/remote_update\.html', parsed.path))
            if not known_path:
                return
            query = parse_qs(parsed.query)
            if query.get('action') == ['actDone'] and query.get('param') in (['0'], ['1']):
                self.values.add(query['param'][0])
    parser = OutcomeFrames()
    parser.feed(html)
    return next(iter(parser.values)) == '1' if len(parser.values) == 1 else None


def process_quizjet_response(request, host, path, response):
    if host not in HOSTS or not path.startswith(('quizjet/', 'quizpet/')) or response.status_code >= 400:
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
    assessment_outcome = None
    if not (correct or wrong) and path.endswith('EvaluateAnswer') and request.POST.get('svc') == 'pretest':
        assessment_outcome = _assessment_result(html)
        correct, wrong = assessment_outcome is True, assessment_outcome is False
    if request.method == 'POST' and request.POST.get('inputans') is not None and (correct or wrong):
        if practice:
            progress = practice
        else:
            progress, _ = ModuleProgress.get_or_create_progress(user=request.user, module=module, course_instance=instance)
        if module_accepts_scored_attempt(progress):
            apply_progress_snapshot(progress, source='quizpet' if path.startswith('quizpet/') else 'quizjet',
                score=max(progress.score or 0, 100 if correct else 0),
                progress=1 if correct else progress.progress, is_complete=progress.is_complete or correct,
                success=correct, event_type='outcome',
                payload={'answer': request.POST.get('inputans'), 'code': request.POST.get('code', ''),
                         'rdfID': request.POST.get('rdfID', ''), 'correct': correct, 'attempt_score': 100 if correct else 0})
            progress.attempts += 1
            progress.save(update_fields=['attempts', 'last_accessed'])
            if assessment_outcome is not None:
                # This tiny legacy iframe refreshes MasteryGrids, not ModuLearn.
                # Read its server-graded outcome above, then prevent an unnecessary
                # upstream request (and its TLS failures). Never accept its GET as
                # a score callback or reveal answers hidden by assessment mode.
                html = re.sub(r'<iframe\b[^>]*>.*?</iframe\s*>',
                    lambda match: '' if _assessment_result(match[0]) is not None else match[0],
                    html, flags=re.I | re.S)
                receipt = ('<div class="modulearn-assessment-receipt" role="status" '
                           'style="margin:1rem 0;padding:.8rem 1rem;border:1px solid #0f766e;'
                           'border-radius:6px;font:16px/1.5 sans-serif">'
                           '<strong>Answer saved.</strong> You can continue to the next activity. '
                           'This assessment does not display correct answers.</div>')
                if re.search(r'</body\s*>', html, re.I):
                    html = re.sub(r'</body\s*>', lambda match: receipt + match[0], html, count=1, flags=re.I)
                else:
                    html += receipt
    fields = ''.join(f'<input type="hidden" name="{key}" value="{escape(value, quote=True)}">' for key,value in context.items())
    html = re.sub(r'(<form\b[^>]*>)', lambda match: match[1]+fields, html, flags=re.I)
    response.content = html.encode('utf-8')
    if response.has_header('Content-Length'):
        response['Content-Length'] = str(len(response.content))
    return response
