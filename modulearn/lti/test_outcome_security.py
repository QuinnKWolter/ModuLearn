import os
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from accounts.models import User
from courses.models import Course, CourseInstance, Enrollment, Unit, Module, ModuleProgress
from lti.models import LTILaunchCache
from lti.tests import outcome_authorization
from lti.services import create_lti_body, get_launch_url


@patch.dict(os.environ, {'CODECHECK_KEY': 'k', 'CODECHECK_SECRET': 's'})
@patch('modulearn.views_lti.LTI_FORWARD_TO_UM', False)
class OutcomeSecurityTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = User.objects.create_user(username='signed-student')
        course = Course.objects.create(id='signed-course', title='Course')
        self.instance = CourseInstance.objects.create(course=course)
        self.module = Module.objects.create(unit=Unit.objects.create(course=course, title='Unit'), title='Exercise',
            provider_id='codecheck', content_url='example', supported_protocols=['lti'])
        Enrollment.objects.create(student=self.user, course_instance=self.instance)
        LTILaunchCache.get_or_create_cache(source_id='signed-test', tool='codecheck', usr=str(self.user.pk),
            grp=str(self.instance.pk), sub='example', module_id=self.module.pk)
        self.xml = '<imsx_POXEnvelopeRequest><imsx_POXBody><replaceResultRequest><resultRecord><sourcedGUID><sourcedId>signed-test</sourcedId></sourcedGUID><result><resultScore><textString>1.0</textString></resultScore></result></resultRecord></replaceResultRequest></imsx_POXBody></imsx_POXEnvelopeRequest>'

    def test_unsigned_and_tampered_outcomes_never_award_credit(self):
        self.assertEqual(self.client.post(reverse('lti_outcome'), self.xml, content_type='application/xml').status_code, 401)
        self.assertEqual(self.client.post(reverse('lti_outcome'), self.xml.replace('1.0', '0.5'),
            content_type='application/xml', HTTP_AUTHORIZATION=outcome_authorization(self.xml)).status_code, 401)
        self.assertFalse(ModuleProgress.objects.filter(score__isnull=False).exists())

    def test_signed_retry_is_idempotent(self):
        authorization = outcome_authorization(self.xml)
        for _ in range(2):
            response = self.client.post(reverse('lti_outcome'), self.xml, content_type='application/xml',
                                        HTTP_AUTHORIZATION=authorization)
            self.assertContains(response, 'success')
        row = ModuleProgress.objects.get(module=self.module)
        self.assertEqual(row.attempts, 1)
        self.assertEqual(row.score, 100)

    def test_launch_requires_authenticated_matching_user(self):
        params = {'tool': 'paws_codecheck', 'usr': str(self.user.pk), 'grp': str(self.instance.pk),
                  'module_id': self.module.pk, 'sub': 'example'}
        self.assertEqual(self.client.get(reverse('lti_launch'), params).status_code, 403)
        self.client.force_login(self.user)
        response = self.client.get(reverse('lti_launch'), params)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(LTILaunchCache.objects.filter(module_id=self.module.pk, tool='codecheck', source_id__startswith='ml-').exists())
        params['sub'] = 'easier-unrelated-problem'
        self.assertEqual(self.client.get(reverse('lti_launch'), params).status_code, 403)
        params['sub'] = 'example'
        params['usr'] = '999999'
        self.assertEqual(self.client.get(reverse('lti_launch'), params).status_code, 403)

    def test_opendsa_json_settings_and_codecheck_host_validation(self):
        body = create_lti_body('opendsa_problems', 'source', 'BSTSumm', '1', '2')
        self.assertEqual(body['custom_ex_settings'], '{}')
        self.assertEqual(body['custom_ex_short_name'], 'BSTSumm')
        with self.assertRaises(ValueError):
            get_launch_url('codecheck', 'https://untrusted.example/lti/problem/files/x')

    @patch.dict(os.environ, {'OPENDSA_PROBLEMS_KEY': 'k', 'OPENDSA_PROBLEMS_SECRET': 's'})
    def test_opendsa_launch_shares_only_origin_for_provider_identification(self):
        self.module.provider_id = 'opendsa_problems'
        self.module.content_url = 'BSTSumm'
        self.module.save()
        self.client.force_login(self.user)
        response = self.client.get(reverse('lti_launch'), {
            'tool': 'opendsa_problems', 'usr': str(self.user.pk), 'grp': str(self.instance.pk),
            'module_id': self.module.pk, 'sub': 'BSTSumm'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Referrer-Policy'], 'origin')

    def test_nonfinite_grade_rejected(self):
        xml = self.xml.replace('1.0', 'NaN')
        self.assertEqual(self.client.post(reverse('lti_outcome'), xml, content_type='application/xml',
            HTTP_AUTHORIZATION=outcome_authorization(xml)).status_code, 400)
        self.assertFalse(ModuleProgress.objects.filter(score__isnull=False).exists())
