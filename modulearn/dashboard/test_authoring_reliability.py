import logging
from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import TestCase, RequestFactory, override_settings

from courses.utils import get_course_auth_token, reset_course_authoring_password
from dashboard.views import generate_course_auth_url, proxy_course_authoring_x_login
from modulearn.request_diagnostics import RequestDiagnosticsMiddleware
from modulearn.logging_utils import request_id_context


class AuthoringReliabilityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='authoring-test',
            email='teacher@example.org', course_authoring_password='private-authoring-password')
        self.request = RequestFactory().post('/dashboard/api/generate_course_auth_url/')
        self.request.user = self.user

    def upstream(self, status, body):
        response = requests.Response()
        response.status_code = status
        response._content = body.encode()
        return response

    def test_rejected_credentials_are_not_reset_retried_or_exposed(self):
        response = self.upstream(422, 'Invalid email or password private-authoring-password')
        with patch('courses.utils.requests.post', return_value=response) as post:
            with self.assertRaises(requests.HTTPError):
                get_course_auth_token(self.user, retry_on_mismatch=True)
            self.assertEqual(post.call_count, 1)
            result = generate_course_auth_url(self.request)
        self.assertEqual(result.status_code, 422)
        self.assertNotIn(b'private-authoring-password', result.content)
        self.assertIn(b'synchronize', result.content)
        self.assertIn('no-store', result['Cache-Control'])
        self.user.refresh_from_db()
        self.assertEqual(self.user.course_authoring_password, 'private-authoring-password')

    def test_timeout_is_a_retryable_service_error(self):
        with patch('courses.utils.requests.post', side_effect=requests.ConnectTimeout('password=private-authoring-password')):
            result = generate_course_auth_url(self.request)
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result['Retry-After'], '30')
        self.assertNotIn(b'private-authoring-password', result.content)

    def test_success_and_explicit_reset_do_not_log_secrets(self):
        response = self.upstream(200, 'private-returned-token')
        with patch('courses.utils.requests.post', return_value=response) as post:
            with self.assertLogs('courses.utils', level='INFO') as logs:
                self.assertEqual(get_course_auth_token(self.user), 'private-returned-token')
                new_password = reset_course_authoring_password(self.user)
        output = '\n'.join(logs.output)
        for secret in ('private-authoring-password', 'private-returned-token', new_password):
            self.assertNotIn(secret, output)
        self.assertFalse(post.call_args.kwargs['allow_redirects'])

    def test_proxy_rejects_invalid_payload_and_sanitizes_remote_errors(self):
        request = RequestFactory().post('/dashboard/api/proxy_x_login/', '[]', content_type='application/json')
        request.user = self.user
        self.assertEqual(proxy_course_authoring_x_login(request).status_code, 400)
        request = RequestFactory().post('/dashboard/api/proxy_x_login/', '{"token":"private-token"}', content_type='application/json')
        request.user = self.user
        with patch('dashboard.views.requests.post', return_value=self.upstream(500, 'private-token')):
            response = proxy_course_authoring_x_login(request)
        self.assertEqual(response.status_code, 502)
        self.assertNotIn(b'private-token', response.content)

    @override_settings(FORCE_SCRIPT_NAME='/modulearn/')
    def test_normalization_preserves_post_and_internal_paths_and_correlates_logs(self):
        request = RequestFactory().post('/ignored', 'submission=code', content_type='application/x-www-form-urlencoded')
        request.path_info = '//proxy/https/provider.example/a//b'
        request.META['QUERY_STRING'] = 'url=https%3A%2F%2Fexample.org%2Fa%2F%2Fb'
        request.META['HTTP_X_REQUEST_ID'] = 'untrusted'
        def view(req):
            self.assertEqual(req.path, '/modulearn/proxy/https/provider.example/a//b')
            self.assertEqual(req.META['PATH_INFO'], req.path_info)
            self.assertEqual(req.body, b'submission=code')
            self.assertEqual(req.META['QUERY_STRING'], 'url=https%3A%2F%2Fexample.org%2Fa%2F%2Fb')
            self.assertEqual(request_id_context.get(), req.request_id)
            return HttpResponse('ok')
        response = RequestDiagnosticsMiddleware(view)(request)
        self.assertEqual(len(response['X-Request-ID']), 32)
        self.assertNotEqual(response['X-Request-ID'], 'untrusted')
        self.assertEqual(request_id_context.get(), '-')

    def test_kt_normalizes_identifier_without_changing_password(self):
        from accounts.knowledgetree_auth import KnowledgeTreeAuthService
        service = KnowledgeTreeAuthService()
        service.auth_enabled = True
        service.auth_method = 'api'
        with patch.object(service, 'authenticate_via_api', return_value={'id': 1}) as authenticate:
            service.authenticate(' test-user ', ' password with spaces ')
        authenticate.assert_called_once_with('test-user', ' password with spaces ')
        self.assertEqual(service._rate_limit_key(' TeSt '), service._rate_limit_key('test'))
        key = service._rate_limit_key(' Ž ' * 200)
        self.assertTrue(key.isascii())
        self.assertLess(len(key), 250)
        self.assertNotIn(' ', key)

    def test_login_fallback_uses_the_cleaned_identifier(self):
        from accounts.views import login_view
        request = RequestFactory().post('/accounts/login/', {'username': ' normalized-user ', 'password': ' exact password '})
        request.session = {}
        with patch('accounts.views.authenticate', return_value=None) as authenticate, \
             patch('accounts.views.messages.error'), patch('accounts.views.render', return_value=HttpResponse()):
            login_view(request)
        self.assertEqual(authenticate.call_args.kwargs['username'], 'normalized-user')
        self.assertEqual(authenticate.call_args.kwargs['password'], ' exact password ')
