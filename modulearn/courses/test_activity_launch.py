import json
from urllib.parse import parse_qs, urlencode, urlsplit

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from courses.models import Course, CourseInstance, Enrollment, Module, ModuleProgress, ModuleProgressEvent, Unit
from modulearn.learning.services.activity_urls import normalize_activity_launch_url
from modulearn.views_proxy import _cache_pcex_activity_metadata, _capture_acos_pcex_event_if_possible, _is_pcex_activity_data_response


class ActivityLaunchURLTests(SimpleTestCase):
    def test_authoring_preview_uses_https_data_and_preserves_goal_index(self):
        original = (
            'http://pawscomp2.sis.pitt.edu/pcex-authoring/preview/index.html?'
            'load=http://pawscomp2.sis.pitt.edu/pcex-authoring/api/hub/68bdb308f6cc3d7a9cc09756?_t=123&index=0'
        )
        for index in ('0', '1', '12'):
            with self.subTest(index=index):
                normalized = urlsplit(normalize_activity_launch_url(original.replace('index=0', f'index={index}')))
                params = parse_qs(normalized.query)
                self.assertEqual(normalized.scheme, 'https')
                self.assertEqual(normalized.netloc, 'acos.cs.vt.edu')
                self.assertEqual(normalized.path, '/pitt/acos-pcex/acos-pcex-examples/')
                self.assertEqual(params['index'], [index])
                self.assertEqual(params['example-id'], ['preview'])
                self.assertEqual(params['load'], ['https://acos.cs.vt.edu/static/acos-pcex-examples/data/68bdb308f6cc3d7a9cc09756.json'])

    def test_unknown_preview_data_sources_are_not_rewritten(self):
        for source in ('http://untrusted.invalid/pcex-authoring/api/hub/68bdb308f6cc3d7a9cc09756',
                       'http://pawscomp2.sis.pitt.edu/other/data.json'):
            url = 'http://pawscomp2.sis.pitt.edu/pcex-authoring/preview/index.html?' + urlencode({'load': source})
            self.assertEqual(normalize_activity_launch_url(url), url)

    def test_java_animation_uses_current_html_entry_point(self):
        self.assertEqual(
            normalize_activity_launch_url('https://acos.cs.vt.edu/pitt/jsvee/jsvee-java/ae?example-id=ae_HelloPrinter'),
            'https://acos.cs.vt.edu/html/jsvee/jsvee-java/ae_HelloPrinter',
        )

    def test_existing_pcex_and_other_provider_urls_are_unchanged(self):
        for url in ('https://acos.cs.vt.edu/html/acos-pcex/acos-pcex-examples/activity__123?index=1',
                    'http://pawscomp2.sis.pitt.edu/pcex/index.html?set=existing',
                    'https://codecheck.io/files/example', ''):
            self.assertEqual(normalize_activity_launch_url(url), url)


class TrackingSession(dict):
    modified = False


class ACOSWorkedExampleTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.student = User.objects.create_user(username='preview-student')
        self.course = Course.objects.create(id='preview-course', title='Preview Course')
        self.instance = CourseInstance.objects.create(course=self.course, group_name='Preview Session')
        self.unit = Unit.objects.create(course=self.course, title='Unit')
        self.module = Module.objects.create(unit=self.unit, title='Example', provider_id='pcex')
        self.other_module = Module.objects.create(unit=self.unit, title='Challenge', provider_id='pcex_ch')
        self.enrollment = Enrollment.objects.create(student=self.student, course_instance=self.instance)
        self.session = TrackingSession()
        self.params = {'cid': self.course.pk, 'grp': self.instance.group_name, 'usr': self.student.username,
                       'module_id': str(self.module.pk), 'example-id': 'preview', 'index': '0'}
        self.referer = 'http://testserver/proxy/https/acos.cs.vt.edu/pitt/acos-pcex/acos-pcex-examples/?' + urlencode(self.params)
        self.data_url = urlsplit('https://acos.cs.vt.edu/static/acos-pcex-examples/data/68bdb308f6cc3d7a9cc09756.json')
        self.activity = [{'activityName': 'example', 'activityGoals': [
            {'id': 'worked', 'name': 'Worked Example', 'fileName': 'Worked.java', 'fullyWorkedOut': True,
             'lineList': [{'number': 1, 'commentList': ['first', 'more detail']}, {'number': 5, 'commentList': ['last']} ]},
            {'id': 'challenge', 'fileName': 'Challenge.java', 'fullyWorkedOut': False, 'lineList': []},
        ]}]

    def cache_data(self):
        request = self.factory.get('/data.json', HTTP_REFERER=self.referer)
        request.session = self.session
        _cache_pcex_activity_metadata(request, self.data_url, json.dumps(self.activity).encode())

    def explanation(self, line, level=1):
        request = self.factory.post('/event', {
            'event': 'log', 'protocolData': json.dumps(self.params),
            'payload': json.dumps({'event_type': 'explanation', 'line_number': line,
                                   'explanation_level': level, 'tracking_id': 'tracking-test'}),
        }, HTTP_REFERER=self.referer)
        request.session = self.session
        request.user = self.student
        _capture_acos_pcex_event_if_possible(request, 'acos.cs.vt.edu',
            'pitt/acos-pcex/acos-pcex-examples/event', HttpResponse('{}'))
        return ModuleProgress.objects.get(module=self.module, enrollment=self.enrollment)

    def test_acos_json_is_recognized_as_activity_metadata(self):
        self.assertTrue(_is_pcex_activity_data_response(self.data_url, 'application/json'))
        self.assertFalse(_is_pcex_activity_data_response(self.data_url, 'text/html'))

    def test_explanations_record_incremental_progress_completion_and_raw_event(self):
        self.cache_data()
        progress = self.explanation(1)
        self.assertAlmostEqual(progress.progress, 1/3)
        self.assertFalse(progress.is_complete)
        self.assertAlmostEqual(self.explanation(1).progress, 1/3)
        self.assertAlmostEqual(self.explanation(1, 2).progress, 2/3)
        progress = self.explanation(5)
        self.assertTrue(progress.is_complete)
        self.assertEqual(progress.score, 100)
        self.assertIsNotNone(progress.completed_at)
        event = ModuleProgressEvent.objects.filter(module_progress=progress, event_type='completion').latest('id')
        self.assertEqual(event.source, 'acos_pcex_worked_example')
        self.assertEqual(event.payload['acos_pcex_event']['payload']['tracking_id'], 'tracking-test')
        self.assertEqual(event.payload['explanation_step_count'], 3)
        other = ModuleProgress.objects.get(module=self.other_module, enrollment=self.enrollment)
        self.assertEqual(other.progress, 0)
        self.enrollment.course_progress.refresh_from_db()
        self.assertEqual(self.enrollment.course_progress.modules_completed, 1)

    def test_missing_metadata_logs_explanation_without_inventing_progress(self):
        progress = self.explanation(1)
        self.assertEqual(progress.progress, 0)
        self.assertTrue(ModuleProgressEvent.objects.filter(module_progress=progress, source='acos_pcex_event').exists())

    def test_selected_challenge_does_not_use_sibling_example_explanations(self):
        self.params['index'] = '1'
        self.referer = self.referer.replace('index=0', 'index=1')
        self.cache_data()
        progress = self.explanation(5)
        self.assertEqual(progress.progress, 0)
        self.assertFalse(progress.is_complete)

    def test_invalid_selected_goal_does_not_cache_another_goal(self):
        self.referer = self.referer.replace('index=0', 'index=999')
        self.cache_data()
        self.assertFalse(self.session.get('pcex_tracking_state'))

    @override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
    def test_student_launch_and_instructor_preview_keep_catalog_example_inside_proxy(self):
        original = ('http://pawscomp2.sis.pitt.edu/pcex-authoring/preview/index.html?'
                    'load=http://pawscomp2.sis.pitt.edu/pcex-authoring/api/hub/68bdb308f6cc3d7a9cc09756&index=0')
        self.module.content_url = original
        self.module.save()
        teacher = User.objects.create_user(username='preview-teacher', is_instructor=True)
        self.course.instructors.add(teacher)
        for user, route, args in (
            (self.student, 'courses:launch_iframe_module', [self.instance.pk, self.module.pk]),
            (teacher, 'courses:preview_iframe_module', [self.module.pk]),
        ):
            with self.subTest(route=route):
                self.client.force_login(user)
                response = self.client.get(reverse(route, args=args))
                self.assertEqual(response.status_code, 200)
                src = response.context['iframe_src']
                self.assertIn('/proxy/https/acos.cs.vt.edu/pitt/acos-pcex/acos-pcex-examples/', src)
                self.assertEqual(parse_qs(urlsplit(src).query)['index'], ['0'])
        self.module.refresh_from_db()
        self.assertEqual(self.module.content_url, original)
