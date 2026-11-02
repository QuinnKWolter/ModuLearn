import json
import tempfile
from pathlib import Path
from urllib.parse import urlencode,urlsplit
from django.test import TestCase, RequestFactory, override_settings
from django.core.management import call_command, CommandError
from django.http import HttpResponse
from accounts.models import User
from courses.models import Course, CourseInstance, Enrollment, Module, ModuleProgress
from modulearn.learning.services.unit_packages import import_unit
from modulearn.learning.services.pcrs_tracking import capture_pcrs_result_if_possible
from modulearn.learning.services.quizjet_tracking import process_quizjet_response


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class LegacyAssessmentTests(TestCase):
    def test_packages_and_individual_answer_history(self):
        teacher=User.objects.create_user(username='RITEL_DEMO_Teacher',is_instructor=True)
        student=User.objects.create_user(username='RITEL_DEMO_Student',is_student=True)
        with tempfile.TemporaryDirectory() as directory:
            call_command('build_legacy_assessment_course',output=directory)
            course=Course.objects.get(pk='cs0401-assessment-lab')
            instance=CourseInstance.objects.get(course=course)
            enrollment=Enrollment.objects.get(course_instance=instance,student=student)
            self.assertEqual(course.units.count(),2)
            self.assertEqual(Module.objects.filter(unit__course=course).count(),20)
            destination=Course.objects.create(id='reused',title='Another course')
            for phase in ['pretest','posttest']:
                payload=json.loads((Path(directory)/(phase+'-unit.json')).read_text(encoding='utf-8'))
                import_unit(destination,payload)
            self.assertEqual(Module.objects.filter(unit__course=destination).count(),20)
            for module in Module.objects.filter(unit__course=course):
                self.assertNotIn('usr=',module.content_url)
                self.assertNotIn('grp=',module.content_url)
                params={'cid':course.pk,'usr':student.username,'course_instance_id':instance.pk,'module_id':module.pk}
                for correct in [False,True]:
                    request=RequestFactory().post('/submit',{'inputans':'11' if correct else 'wrong','submission':'result = a == b && b == c;','code':'reference snapshot','svc':'pretest'})
                    request.user=student
                    request.META['HTTP_REFERER']='http://testserver/embed?'+urlencode(params)
                    if module.provider_id=='quizjet':
                        response=HttpResponse('<iframe src="/proxy/https/adapt2.sis.pitt.edu/um-vis-notificator/remote_update.html?action=actDone&amp;param='+('1' if correct else '0')+'"></iframe>',content_type='text/html')
                        processed = process_quizjet_response(request,'adapt2.sis.pitt.edu','quizjet/EvaluateAnswer',response)
                        self.assertContains(processed, 'Answer saved.')
                        self.assertNotContains(processed, 'remote_update.html')
                        self.assertNotContains(processed, 'CORRECT!')
                    else:
                        response=HttpResponse(json.dumps({'score':1 if correct else 0,'max_score':1}),content_type='application/json')
                        capture_pcrs_result_if_possible(request,'pcrs.utm.utoronto.ca',urlsplit(module.content_url).path.strip('/').replace('/embed','/run'),response)
                progress=ModuleProgress.objects.get(enrollment=enrollment,module=module)
                self.assertEqual(progress.attempts,2)
                self.assertTrue(progress.is_complete)
                events=list(progress.events.filter(source=module.provider_id, event_type__in=['outcome'] if module.provider_id=='quizjet' else ['progress','completion']).order_by('id'))
                self.assertEqual(len(events),2)
                self.assertTrue(events[0].created_at)
                if module.provider_id=='pcrs':
                    self.assertEqual(events[0].payload['pcrs_result']['score'],0)
                    self.assertEqual(events[1].payload['pcrs_submission']['form']['submission'],'result = a == b && b == c;')
                else:
                    self.assertEqual(events[0].payload['attempt_score'],0)
                    self.assertEqual(events[1].payload['answer'],'11')
            with self.assertRaises(CommandError):call_command('build_legacy_assessment_course',output=directory)
            self.assertEqual(Module.objects.filter(unit__course=course).count(),20)

    def test_assessment_outcome_only_accepts_known_unambiguous_notifications(self):
        from modulearn.learning.services.quizjet_tracking import _assessment_result
        self.assertIsNone(_assessment_result('<p>param=1</p>'))
        self.assertIsNone(_assessment_result('<iframe src="https://example.org/um-vis-notificator/remote_update.html?action=actDone&param=1"></iframe>'))
        self.assertTrue(_assessment_result('<iframe src="/modulearn/proxy/https/adapt2.sis.pitt.edu/um-vis-notificator/remote_update.html?action=actDone&amp;param=1"></iframe>'))
        self.assertFalse(_assessment_result('<iframe src="https://adapt2.sis.pitt.edu/um-vis-notificator/remote_update.html?action=actDone&param=0"></iframe>'))
        self.assertIsNone(_assessment_result(''.join('<iframe src="/um-vis-notificator/remote_update.html?action=actDone&param='+str(i)+'"></iframe>' for i in [0,1])))
