import json
from unittest.mock import patch
from urllib.parse import urlencode
from django.test import RequestFactory, TestCase
from django.http import HttpResponse
from accounts.models import User
from courses.models import Course, CourseInstance, Unit, Module, Enrollment, ModuleProgress, RecommendationActivation, RecommendationProgress
from modulearn.learning.services.sqlknot_tracking import capture_sqlknot_result


class SQLKnotTrackingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='sql-student')
        self.course = Course.objects.create(id='sql-test', title='SQL', plugin_config={'plugins': {'static_recommendations': {'enabled': True}}})
        self.instance = CourseInstance.objects.create(course=self.course, group_name='SQL')
        self.unit = Unit.objects.create(course=self.course, title='SELECT')
        self.module = Module.objects.create(unit=self.unit, title='SELECT FROM', content_url='https://adapt2.sis.pitt.edu/sqlknot/index.html?cid=9&tid=1')
        self.enrollment = Enrollment.objects.create(student=self.user, course_instance=self.instance)

    def capture(self, result, *, endpoint='CheckAnswer', token=None, instance=None):
        params = {'cid': '9', 'module_id': self.module.pk, 'course_instance_id': instance or self.instance.pk}
        if token:
            params['recommendation'] = str(token)
        request = RequestFactory().post('/proxy', json.dumps({'answer': 'SELECT * FROM actor;', 'questionId': 7, 'actionType': 'check_answer'}),
            content_type='application/json', HTTP_REFERER='http://testserver/proxy/https/adapt2.sis.pitt.edu/sqlknot/index.html?' + urlencode(params))
        request.user = self.user
        capture_sqlknot_result(request, 'adapt2.sis.pitt.edu', 'sqlknotserver/' + endpoint, HttpResponse(json.dumps(result)))

    def test_wrong_correct_and_interactions_log_exact_session(self):
        self.capture({'checkResult': False})
        self.capture({'checkResult': True})
        self.capture({'ok': True}, endpoint='Track')
        row = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.module)
        self.assertEqual(row.attempts, 2)
        self.assertEqual(row.score, 100)
        self.assertTrue(row.is_complete)
        self.assertTrue(row.events.filter(event_type='provider_event').exists())
        self.assertTrue(row.events.filter(payload__sqlknot_result__checkResult=False).exists())
        self.assertEqual(list(row.events.filter(event_type='attempt').order_by('id').values_list('score', flat=True)), [0, 100])

    def test_invalid_or_foreign_context_does_not_award_credit(self):
        self.capture({'checkResult': 'false'})
        self.capture({'checkResult': True}, instance=99999)
        self.assertFalse(ModuleProgress.objects.filter(is_complete=True).exists())

    def test_recommendation_remains_separate(self):
        from courses.models import StaticRecommendationSet
        StaticRecommendationSet.objects.create(course=self.course, course_instance=self.instance, enabled=True)
        activation = RecommendationActivation.objects.create(enrollment=self.enrollment, source_module=self.module)
        item = RecommendationProgress.objects.create(activation=activation, module=self.module, provider='sqlknot', rank=1, similarity=1)
        self.capture({'checkResult': True}, token=item.pk)
        item.refresh_from_db()
        self.assertEqual(item.score, 100)
        self.assertTrue(item.events.filter(event_type='attempt').exists())
        self.assertFalse(ModuleProgress.objects.filter(is_complete=True).exists())

    def test_instructor_grade_is_not_student_data(self):
        self.instance.instructors.add(self.user)
        # Also hide an older ordinary enrollment as soon as the user becomes
        # an instructor, even before their first testing launch flags it.
        self.assertFalse(Enrollment.objects.filter(pk=self.enrollment.pk).exists())
        self.capture({'checkResult': True})
        row = ModuleProgress.objects.get(user=self.user, module=self.module)
        self.assertEqual(row.score, 100)
        self.assertTrue(row.enrollment.is_instructor_preview)
        self.assertFalse(self.instance.enrollments.exists())

    @patch('modulearn.learning.services.annotated_tracking._fetch')
    def test_annotated_lines_complete_only_after_all_comments_open(self, fetch):
        from django.core.cache import cache
        from modulearn.learning.services.splice_tracking import record_splice_event
        cache.clear()
        fetch.return_value = '''<script>window.annotated = {'test': {"lines": [{"comment":"a"},{"comment":""},{"comment":"b"}]}};</script>'''
        self.module.content_url = 'https://acos.cs.vt.edu/html/annotated/acos-annex-sql/test'
        self.module.save()
        progress, _ = ModuleProgress.get_or_create_progress(user=self.user, module=self.module, course_instance=self.instance)
        def opened(line, identity):
            record_splice_event(progress, {'event_id': identity, 'message': {
                'subject': 'SPLICE.sendEvent', 'data': {'exampleId': 'test', 'type': 'open', 'line': line}}})
            progress.refresh_from_db()
        opened('1', 'first')
        self.assertEqual(progress.score, 50)
        self.assertFalse(progress.is_complete)
        opened('1', 'first')
        opened('2', 'not-annotated')
        self.assertFalse(progress.is_complete)
        opened('3', 'last')
        self.assertTrue(progress.is_complete)
        self.assertEqual(progress.score, 100)
        self.assertEqual(progress.attempts, 0)  # Reading is not an answer submission.
        self.assertEqual(fetch.call_count, 1)

    @patch('modulearn.learning.services.annotated_tracking.annotation_metadata')
    def test_annotation_metadata_outage_preserves_opens_for_reconciliation(self, metadata):
        from modulearn.learning.services.splice_tracking import record_splice_event
        metadata.side_effect = [None, {'example': 'test', 'lines': ['1', '3']}]
        progress, _ = ModuleProgress.get_or_create_progress(user=self.user, module=self.module, course_instance=self.instance)
        for line in ['1', '3']:
            record_splice_event(progress, {'event_id': line, 'message': {
                'subject': 'SPLICE.sendEvent', 'data': {'exampleId': 'test', 'type': 'open', 'line': line}}})
        progress.refresh_from_db()
        self.assertTrue(progress.is_complete)
        self.assertEqual(progress.score, 100)
        self.assertEqual(progress.events.filter(event_type='provider_event').count(), 2)

    def test_dbqa_steps_and_logs_are_scoped_to_authenticated_learner(self):
        from lti.models import LTILaunchCache
        from modulearn.learning.services.dbqa_tracking import capture_dbqa_result
        launch = LTILaunchCache.get_or_create_cache(source_id='dbqa-test', tool='paws_dbqa',
            usr=str(self.user.pk), grp=str(self.instance.pk), sub='select-from-1', module_id=self.module.pk)
        for score in ('0.5', '1', '0.2'):
            request = RequestFactory().post('/proxy', {'sourcedid': launch.source_id, 'score': score})
            request.user = self.user
            capture_dbqa_result(request, 'codesmell.org', 'dbqa/lti/1.1/result/send', HttpResponse('ok'))
        row = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.module)
        self.assertEqual(row.score, 100)
        self.assertTrue(row.is_complete)
        self.assertEqual(row.events.filter(source='dbqa', event_type='provider_event').count(), 3)
        outsider = User.objects.create_user(username='dbqa-outsider')
        request.user = outsider
        capture_dbqa_result(request, 'codesmell.org', 'dbqa/lti/1.1/result/send', HttpResponse('ok'))
        self.assertFalse(ModuleProgress.objects.filter(user=outsider).exists())
