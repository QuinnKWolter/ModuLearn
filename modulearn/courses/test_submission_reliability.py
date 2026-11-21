import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlparse
from unittest.mock import patch, MagicMock

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory, override_settings
from courses.models import Course, CourseInstance, Unit, Module, Enrollment, ModuleProgress, ModuleProgressEvent
from modulearn.views_proxy import http_get_proxy_path, _upstream_timeout, _inject_activity_api_rewrite_script
from modulearn.learning.services.progress import apply_progress_snapshot
from modulearn.logging_utils import RedactingFormatter


class SubmissionReliabilityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='test-submissions')
        self.course = Course.objects.create(id='submission-test', title='Submission test')
        self.instance = CourseInstance.objects.create(course=self.course, group_name='Test')
        unit = Unit.objects.create(course=self.course, title='Unit')
        self.module = Module.objects.create(unit=unit, title='While Loop 2', content_url='https://pcrs.utm.utoronto.ca/mgrids/problems/java/358/embed?act=PCRS&sub=while2_coding')
        self.enrollment = Enrollment.objects.create(student=self.user, course_instance=self.instance)
        self.progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.module)

    def request(self):
        request = RequestFactory().post('/proxy/https/pcrs.utm.utoronto.ca/mgrids/problems/java/358/run', 'submission=count+%3D+0%3B', content_type='application/x-www-form-urlencoded')
        request.session = {}
        request.user = self.user
        request.META['HTTP_REFERER'] = ('http://testserver/proxy/https/pcrs.utm.utoronto.ca/mgrids/problems/java/358/embed'
            f'?cid={self.course.pk}&usr={self.user.username}&module_id={self.module.pk}&course_instance_id={self.instance.pk}')
        return request

    def test_timeout_is_scoped_to_pcrs_run_posts(self):
        run = urlparse('https://pcrs.utm.utoronto.ca/mgrids/problems/java/358/run')
        self.assertEqual(_upstream_timeout('POST', run), (5, 30))
        self.assertEqual(_upstream_timeout('GET', run), 8)
        self.assertEqual(_upstream_timeout('POST', urlparse('https://example.org/mgrids/problems/java/358/run')), 8)
        self.assertEqual(_upstream_timeout('POST', urlparse('https://pcrs.utm.utoronto.ca/mgrids/problems/java/358/embed')), 8)

    def test_real_delayed_http_response_exceeding_old_limit_is_recorded(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                time.sleep(9)  # A real network read exceeding the former eight-second limit.
                body = b'{"score": 8, "max_score": 8, "results": []}'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        original_post = requests.post

        def local_upstream(url, **kwargs):
            return original_post(f'http://127.0.0.1:{server.server_port}/run', **kwargs)

        try:
            with patch('modulearn.views_proxy.requests.post', side_effect=local_upstream) as post:
                response = http_get_proxy_path(self.request(), 'https/pcrs.utm.utoronto.ca/mgrids/problems/java/358/run')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(post.call_count, 1)
            self.progress.refresh_from_db()
            self.assertTrue(self.progress.is_complete)
            self.assertEqual(self.progress.score, 100)
            self.assertEqual(self.progress.attempts, 1)
            event = ModuleProgressEvent.objects.get(module_progress=self.progress, event_type='completion')
            self.assertEqual(event.payload['pcrs_submission']['form']['submission'], 'count = 0;')
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    @patch('modulearn.views_proxy.requests.post', side_effect=requests.ReadTimeout('sid=secret-token'))
    def test_timeout_does_not_record_failure_or_retry(self, post):
        response = http_get_proxy_path(self.request(), 'https/pcrs.utm.utoronto.ca/mgrids/problems/java/358/run')
        self.assertEqual(response.status_code, 504)
        self.assertNotIn(b'secret-token', response.content)
        self.assertEqual(post.call_count, 1)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.attempts, 0)
        receipt = ModuleProgressEvent.objects.get(module_progress=self.progress, source='pcrs_transport')
        self.assertEqual(receipt.payload['status'], 'failed')
        self.assertEqual(receipt.payload['http_status'], 504)
        self.assertEqual(receipt.payload['pcrs_submission']['form']['submission'], 'count = 0;')
        self.assertIsNone(receipt.score)
        self.assertFalse(ModuleProgressEvent.objects.filter(module_progress=self.progress, event_type='attempt').exists())

    def test_stale_worked_example_callbacks_cannot_undo_completion(self):
        for source in ('pcex_worked_example', 'acos_pcex_worked_example'):
            stale = ModuleProgress.objects.get(pk=self.progress.pk)
            apply_progress_snapshot(self.progress, source=source, progress=1, score=100, success=True, is_complete=True)
            completed_at = self.progress.completed_at
            apply_progress_snapshot(stale, source=source, progress=6/9, score=100*6/9, success=False,
                                    is_complete=False, payload={'incoming_steps': 6})
            self.progress.refresh_from_db()
            self.assertEqual(self.progress.progress, 1)
            self.assertEqual(self.progress.score, 100)
            self.assertTrue(self.progress.is_complete)
            self.assertEqual(self.progress.completed_at, completed_at)
        self.assertFalse(ModuleProgressEvent.objects.filter(module_progress=self.progress, event_type='reopened').exists())

    def test_credentials_redacted_in_formatted_messages_and_tracebacks(self):
        formatter = RedactingFormatter('%(message)s')
        try:
            raise ValueError('https://host/run?sid=exception-secret&module_id=8')
        except ValueError:
            import sys
            record = logging.LogRecord('test', logging.ERROR, '', 0,
                'URL %s; cookies sessionid=cookie-secret; data %s',
                ('/proxy/?sid=launch-secret&module_id=8&url=https%3A%2F%2Fhost%3Fpwd%3Dencoded-secret%26act%3Dx', {'pwd': 'form-secret', 'sid': ['list-secret']}), sys.exc_info())
        result = formatter.format(record)
        for secret in ('exception-secret', 'launch-secret', 'cookie-secret', 'form-secret', 'encoded-secret', 'list-secret'):
            self.assertNotIn(secret, result)
        self.assertIn('module_id=8', result)

    def test_empty_kt_groups_are_reused_only_on_current_user_instance(self):
        from dashboard.kt_utils import get_user_groups_with_course_ids
        user = SimpleNamespace(username='test', kt_user_id=5, kt_login='test')
        with patch('dashboard.kt_utils.get_user_groups_from_kt_db', return_value=[]) as groups:
            self.assertEqual(get_user_groups_with_course_ids(user), [])
            self.assertEqual(get_user_groups_with_course_ids(user), [])
            self.assertEqual(groups.call_count, 1)
            get_user_groups_with_course_ids(SimpleNamespace(username='test', kt_user_id=5, kt_login='test'))
            self.assertEqual(groups.call_count, 2)

    def test_failed_kt_authentication_is_not_logged_as_success(self):
        from accounts.knowledgetree_auth import KnowledgeTreeAuthService
        response = MagicMock()
        response.json.return_value = {'loggedin': False, 'error': 'Incorrect password'}
        with patch('accounts.knowledgetree_auth.requests.get', return_value=response):
            with self.assertLogs('accounts.knowledgetree_auth', level='INFO') as logs:
                auth = KnowledgeTreeAuthService()
                auth.auth_enabled = True
                self.assertIsNone(auth.authenticate_via_api('test', 'test-password'))
        self.assertNotIn('authentication successful', '\n'.join(logs.output))

    @override_settings(FORCE_SCRIPT_NAME='/modulearn/')
    def test_proxy_launch_prefix_has_one_separator(self):
        from courses.views import to_path_style_proxy
        from modulearn.views_proxy import _to_path_style
        url = 'https://pcrs.utm.utoronto.ca/mgrids/problems/java/358/embed?act=PCRS'
        for convert in (to_path_style_proxy, _to_path_style):
            self.assertTrue(convert(url).startswith('/modulearn/proxy/'))
        injected = _inject_activity_api_rewrite_script('<html><head></head></html>')
        self.assertIn('const moduLearnPrefix = "/modulearn"', injected)

    def test_receipt_saved_before_upstream_and_visible_in_activity_export(self):
        from dashboard.activity_data import rows, snapshot
        def timeout(url, **kwargs):
            receipt = ModuleProgressEvent.objects.get(source='pcrs_transport')
            self.assertEqual(receipt.payload['status'], 'pending')
            raise requests.ReadTimeout('upstream unavailable')
        request = self.request()
        request.META['HTTP_REFERER'] += '&sid=private-session'
        with patch('modulearn.views_proxy.requests.post', side_effect=timeout):
            response = http_get_proxy_path(request, 'https/pcrs.utm.utoronto.ca/mgrids/problems/java/358/run')
        self.assertEqual(response.status_code, 504)
        exported = rows(self.instance, 'course', {}, snapshot(self.instance, 'course', {}), payload=True)
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]['payload']['status'], 'failed')
        self.assertNotIn('private-session', str(exported))
        self.assertIn('count = 0;', str(exported))

    def test_receipts_for_practice_remain_separate(self):
        from courses.models import RecommendationActivation, RecommendationProgress, RecommendationEvent
        from modulearn.learning.services.pcrs_tracking import record_pcrs_submission, finish_pcrs_submission
        from django.http import HttpResponse
        activation = RecommendationActivation.objects.create(enrollment=self.enrollment, source_module=self.module)
        item = RecommendationProgress.objects.create(activation=activation, module=self.module, provider='pcrs', rank=1, similarity=1)
        request = self.request()
        request.META['HTTP_REFERER'] += '&recommendation=' + str(item.pk)
        with patch('modulearn.learning.services.recommendation_tracking.recommendations_enabled', return_value=True):
            receipt = record_pcrs_submission(request, 'pcrs.utm.utoronto.ca', 'mgrids/problems/java/358/run')
        finish_pcrs_submission(receipt, HttpResponse(status=504))
        event = RecommendationEvent.objects.get(recommendation=item)
        self.assertEqual(event.payload['status'], 'failed')
        self.assertIsNone(event.score)
        self.assertFalse(ModuleProgressEvent.objects.exists())
        item.refresh_from_db()
        self.assertEqual(item.attempts, 0)
        self.assertEqual(item.progress, 0)

    def test_untracked_preview_and_stale_replacement_do_not_get_receipts(self):
        from modulearn.learning.services.pcrs_tracking import record_pcrs_submission
        request = self.request()
        request.META['HTTP_REFERER'] = request.META['HTTP_REFERER'].replace(self.user.username, 'preview-test')
        self.assertIsNone(record_pcrs_submission(request, 'pcrs.utm.utoronto.ca', 'mgrids/problems/java/358/run'))
        self.module.content_url = 'https://pcrs.utm.utoronto.ca/mgrids/problems/java/478/embed'
        self.module.save(update_fields=['content_url'])
        self.assertIsNone(record_pcrs_submission(self.request(), 'pcrs.utm.utoronto.ca', 'mgrids/problems/java/358/run'))
        self.assertFalse(ModuleProgressEvent.objects.exists())

    def test_receipt_failure_prevents_unlogged_upstream_submission(self):
        from django.db import DatabaseError
        with patch('modulearn.views_proxy.record_pcrs_submission', side_effect=DatabaseError('secret database details')), \
             patch('modulearn.views_proxy.requests.post') as post:
            response = http_get_proxy_path(self.request(), 'https/pcrs.utm.utoronto.ca/mgrids/problems/java/358/run')
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(b'secret database details', response.content)
        post.assert_not_called()

    def test_failed_local_grade_handling_retains_returned_result(self):
        from modulearn.learning.services.pcrs_tracking import record_pcrs_submission, finish_pcrs_submission
        from django.http import HttpResponse
        receipt = record_pcrs_submission(self.request(), 'pcrs.utm.utoronto.ca', 'mgrids/problems/java/358/run')
        finish_pcrs_submission(receipt, HttpResponse('{"score": 3, "max_score": 8}', content_type='application/json'))
        event = ModuleProgressEvent.objects.get(source='pcrs_transport')
        self.assertEqual(event.payload['status'], 'ungraded_response')
        self.assertEqual(event.payload['pcrs_result']['score'], 3)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.attempts, 0)
