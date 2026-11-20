import csv
import io
import json
import tempfile
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs

from django.test import TestCase, override_settings
from django.urls import reverse, resolve
from django.http import StreamingHttpResponse

from accounts.models import User
from courses.models import (Course, CourseInstance, Unit, Module, Enrollment, ModuleProgress,
                            ModuleProgressEvent, ModuleAccessLog, RecommendationActivation,
                            RecommendationProgress, RecommendationEvent)
from dashboard import activity_exports as exports


def follow_activity_export(client, response):
    """Follow the old CSV URL's preparation redirect in regression tests."""
    if response.status_code != 302:
        return response
    target = urlsplit(response['Location'])
    instance_id = resolve(target.path).kwargs['instance_id']
    options = {key: values[0] for key, values in parse_qs(target.query).items()}
    with tempfile.TemporaryDirectory() as directory, override_settings(ACTIVITY_EXPORT_ROOT=directory):
        url = reverse('dashboard:activity_prepare', args=[instance_id])
        result = client.post(url, json.dumps(options), content_type='application/json').json()
        for _ in range(1000):
            result = client.post(url, json.dumps({'token': result['token']}), content_type='application/json').json()
            if result['done']:
                downloaded = client.get(result['download'])
                content = b''.join(downloaded.streaming_content)
                downloaded.close()
                return StreamingHttpResponse([content], content_type='text/csv')
        raise AssertionError('Export never completed')


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ActivityBrowserTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user('activity-teacher', is_instructor=True)
        cls.student = User.objects.create_user('=spreadsheet()', full_name='Élodie', email='learner@example.test')
        cls.other = User.objects.create_user('other-teacher', is_instructor=True)
        cls.course = Course.objects.create(id='activity-lab', title='Activity lab')
        cls.instance = CourseInstance.objects.create(course=cls.course, group_name='One')
        cls.instance.instructors.add(cls.teacher)
        cls.unit = Unit.objects.create(course=cls.course, title='Unit')
        cls.module = Module.objects.create(unit=cls.unit, title='Step Counter', content_data={'huge': 'x' * 10000})
        cls.enrollment = Enrollment.objects.create(course_instance=cls.instance, student=cls.student)
        cls.progress, _ = ModuleProgress.objects.get_or_create(enrollment=cls.enrollment, module=cls.module, user=cls.student)
        cls.event = ModuleProgressEvent.objects.create(course_instance=cls.instance, user=cls.student,
            module=cls.module, module_progress=cls.progress, event_type='attempt', score=75, progress=.75,
            payload={'response': '<script>unsafe</script>', 'tests': [1, 1, 1, 0]})
        cls.activation = RecommendationActivation.objects.create(enrollment=cls.enrollment, source_module=cls.module)
        cls.recommendation = RecommendationProgress.objects.create(activation=cls.activation, module=cls.module, rank=1, similarity=.9, provider='cupcake')
        RecommendationEvent.objects.create(activation=cls.activation, recommendation=cls.recommendation, event_type='visit', payload={'practice': True})
        ModuleAccessLog.objects.create(enrollment=cls.enrollment, user=cls.student, course_instance=cls.instance, module=cls.module, event_type='launch')

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        override = override_settings(ACTIVITY_EXPORT_ROOT=self.directory.name)
        override.enable(); self.addCleanup(override.disable)
        self.client.force_login(self.teacher)
        self.events = reverse('dashboard:activity_events', args=[self.instance.pk])
        self.prepare = reverse('dashboard:activity_prepare', args=[self.instance.pk])

    def post(self, body):
        return self.client.post(self.prepare, json.dumps(body), content_type='application/json')

    def finish(self, options):
        state = self.post(options).json()
        for _ in range(30):
            state = self.post({'token': state['token']}).json()
            if state['done']:
                response = self.client.get(state['download'])
                raw = b''.join(response.streaming_content).decode('utf-8'); response.close()
                return list(csv.DictReader(io.StringIO(raw))), state
        self.fail('Export did not finish')

    def test_lazy_payload_search_filters_and_permissions(self):
        with self.assertNumQueries(7):
            # Authentication/session + scoped ownership + max ID + rows + facets.
            response = self.client.get(self.events, {'q': 'Élodie', 'event': 'attempt'})
        rows = response.json()['rows']
        self.assertEqual(len(rows), 1)
        self.assertNotIn('payload', rows[0])
        self.assertEqual(rows[0]['attempt_score'], 75)
        self.assertEqual(self.client.get(self.events, {'detail': self.event.pk}).json()['payload']['tests'], [1, 1, 1, 0])
        self.assertEqual(self.client.get(self.events, {'from': 'not-date'}).status_code, 400)
        self.assertEqual(self.client.get(self.events, {'from': '2099-01-01'}).json()['rows'], [])
        other = CourseInstance.objects.create(course=self.course, group_name='Other')
        foreign = ModuleProgressEvent.objects.create(course_instance=other, user=self.student, module=self.module,
            module_progress=self.progress, event_type='attempt')
        self.assertEqual(self.client.get(self.events, {'detail': foreign.pk}).status_code, 404)
        for user in (self.student, self.other):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.events).status_code, 403)
            self.assertEqual(self.post({}).status_code, 403)

    def test_pages_and_export_snapshot_have_no_gaps_or_duplicates(self):
        ModuleProgressEvent.objects.bulk_create([ModuleProgressEvent(course_instance=self.instance, user=self.student,
            module=self.module, module_progress=self.progress, event_type='provider_event', payload={'n': n}) for n in range(2100)])
        page = self.client.get(self.events).json()
        ids = [row['id'] for row in page['rows']]
        ticket = self.post({'context': 'course'}).json()['token']
        newer = ModuleProgressEvent.objects.create(course_instance=self.instance, user=self.student,
            module=self.module, module_progress=self.progress, event_type='new')
        while page['next']:
            page = self.client.get(self.events, {'cursor': page['next']}).json()
            ids += [row['id'] for row in page['rows']]
        self.assertEqual(len(ids), 2101)
        self.assertEqual(len(set(ids)), 2101)
        self.assertNotIn(newer.pk, ids)
        state = self.post({'token': ticket}).json()
        while not state['done']:
            state = self.post({'token': ticket}).json()
        response = self.client.get(state['download'])
        rows = list(csv.DictReader(io.StringIO(b''.join(response.streaming_content).decode()))); response.close()
        self.assertEqual([int(row['id']) for row in rows], ids)
        self.assertEqual(self.post({'token': ticket}).json()['count'], 2101)

    def test_retry_truncates_uncommitted_bytes_and_preserves_payload(self):
        token = self.post({'context': 'all'}).json()['token']
        path = exports.locate(token, self.instance, self.teacher)
        with patch.object(exports, 'save_state', side_effect=OSError('disk interrupted')):
            with self.assertRaises(OSError): exports.advance(path, self.instance)
        state = self.post({'token': token}).json()
        while not state['done']: state = self.post({'token': token}).json()
        response = self.client.get(state['download'])
        rows = list(csv.DictReader(io.StringIO(b''.join(response.streaming_content).decode()))); response.close()
        self.assertEqual(len(rows), 3)
        self.assertEqual({row['context'] for row in rows}, {'course', 'practice', 'access'})
        record = next(row for row in rows if row['context'] == 'course')
        self.assertEqual(record['student'], "'=spreadsheet()")
        self.assertEqual(json.loads(record['payload'])['tests'], [1, 1, 1, 0])
        self.assertEqual(record['attempt_score'], '75.0')
        self.assertEqual(ModuleProgress.objects.get(pk=self.progress.pk).attempts, 0)

    def test_concurrent_prepare_and_unready_download_are_rejected(self):
        ticket = self.post({'context': 'course'}).json()['token']
        path = exports.locate(ticket, self.instance, self.teacher)
        with exports.locked(path):
            self.assertEqual(self.post({'token': ticket}).status_code, 409)
        self.assertEqual(self.client.get(reverse('dashboard:activity_download', args=[self.instance.pk]), {'token': ticket}).status_code, 409)
        self.assertTrue(self.post({'token': ticket}).json()['done'])

    def test_summary_unvisited_items_and_private_downloads(self):
        rows, state = self.finish({'context': 'summary'})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['visits'], '1')
        self.assertEqual(rows[0]['submissions'], '0')
        self.assertEqual(rows[0]['ranking_method'], 'cosine_similarity')
        self.instance.instructors.add(self.other)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(state['download']).status_code, 400)
        self.assertEqual(self.post({'token': state['token']}).status_code, 400)
        self.client.force_login(self.teacher)
        self.instance.instructors.remove(self.teacher)
        self.assertEqual(self.client.get(state['download']).status_code, 403)

    def test_preview_events_excluded_and_filters_match_export(self):
        preview = Enrollment.objects.create(course_instance=self.instance, student=self.teacher, is_instructor_preview=True)
        progress, _ = ModuleProgress.objects.get_or_create(enrollment=preview, module=self.module, user=self.teacher)
        ModuleProgressEvent.objects.create(course_instance=self.instance, user=self.teacher, module=self.module,
            module_progress=progress, event_type='attempt')
        options = {'q': 'Step Counter', 'event': 'attempt', 'context': 'course'}
        rows, _ = self.finish(options)
        listed = self.client.get(self.events, options).json()['rows']
        self.assertEqual([int(row['id']) for row in rows], [row['id'] for row in listed])
        self.assertEqual(len(rows), 1)

    def test_legacy_events_without_session_field_are_not_lost(self):
        legacy = ModuleProgressEvent.objects.create(course_instance=None, user=self.student, module=self.module,
            module_progress=self.progress, event_type='completion', progress=1, success=True)
        rows, _ = self.finish({'context': 'course'})
        self.assertIn(str(legacy.pk), [row['id'] for row in rows])
        self.assertEqual(len(self.client.get(self.events).json()['rows']), 2)

    def test_related_practice_filters_by_original_and_student(self):
        different = Module.objects.create(unit=self.unit, title='Another original problem')
        activation = RecommendationActivation.objects.create(enrollment=self.enrollment, source_module=different)
        RecommendationEvent.objects.create(activation=activation, event_type='activated')
        filters = {'context': 'practice', 'original': self.module.pk, 'student': self.student.pk}
        records = self.client.get(self.events, filters).json()['rows']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['source_module_id'], self.module.pk)
        exported, _ = self.finish(filters)
        self.assertEqual(len(exported), 1)

    def test_dashboard_and_old_links_use_bounded_preparation(self):
        response = self.client.get(reverse('dashboard:instructor_dashboard'))
        self.assertContains(response, 'activityBrowser')
        self.assertNotContains(response, 'sessionActivityData-')
        for kind, expected in [('course_csv', 'course'), ('csv', 'practice'), ('summary', 'summary')]:
            response = self.client.get(reverse('courses:recommendation_logs', args=[self.instance.pk]), {'download': kind})
            self.assertEqual(response.status_code, 302)
            self.assertIn('context=' + expected, response['Location'])
            self.assertContains(self.client.get(response['Location']), 'activityExportPage')
