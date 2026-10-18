from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from courses.models import Course, CourseInstance, Unit, Module
from lti.models import LTILaunchCache, LTIOutcomeLog


class IntegrationTestingTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='teacher', is_instructor=True)
        self.student = User.objects.create_user(username='student')
        self.other = User.objects.create_user(username='other', is_instructor=True)
        course = Course.objects.create(id='integration', title='Integration')
        self.instance = CourseInstance.objects.create(course=course, group_name='Lab')
        self.instance.instructors.add(self.teacher)
        unit = Unit.objects.create(course=course, title='LTI')
        self.module = Module.objects.create(unit=unit, title='Example', supported_protocols=['lti'])
        self.url = reverse('courses:integration_testing', args=[self.instance.pk])

    def test_requires_session_instructor(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        for user in (self.student, self.other):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_redacted_and_scoped_evidence_does_not_mutate(self):
        launch = LTILaunchCache.objects.create(source_id='private-source', tool='example', usr=str(self.teacher.pk),
            grp=str(self.instance.pk), user_id=self.teacher.pk, course_instance_id=self.instance.pk,
            module_id=self.module.pk, sub='private-sub', sid='private-session', expires_at=timezone.now()+timedelta(hours=1))
        LTIOutcomeLog.objects.create(source_id=launch.source_id, score_raw='1', score_normalized=1,
            success=True, error_message='private-error')
        other = LTILaunchCache.objects.create(source_id='student-source', tool='example', usr=str(self.student.pk),
            grp=str(self.instance.pk), user_id=self.student.pk, course_instance_id=self.instance.pk,
            module_id=self.module.pk, expires_at=timezone.now()+timedelta(hours=1))
        LTIOutcomeLog.objects.create(source_id=other.source_id, score_raw='0', success=False)
        self.client.force_login(self.teacher)
        response = self.client.get(self.url+'?format=json')
        self.assertEqual(response.status_code, 200)
        row = response.json()['modules'][0]
        self.assertEqual(row['lti_launches'], 1)
        self.assertEqual(len(row['outcomes']), 1)
        self.assertTrue(row['outcomes'][0]['success'])
        for secret in ('private-source', 'private-sub', 'private-session', 'private-error', 'student-source'):
            self.assertNotContains(response, secret)
        self.assertEqual(self.instance.enrollments.count(), 0)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertContains(self.client.get(self.url), 'Integration testing')
