import json
import tempfile
from pathlib import Path
from django.test import TestCase, RequestFactory, override_settings
from django.http import HttpResponse
from django.urls import reverse
from urllib.parse import urlencode, urlsplit
from django.core.management import call_command
from accounts.models import User
from courses.models import Course, CourseInstance, Module, ModuleProgress, Enrollment, Unit
from modulearn.learning.services.progress import apply_progress_snapshot
from modulearn.learning.services.access_rules import evaluate_module_access, evaluate_unit_access
from modulearn.learning.services.unit_packages import import_unit


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CompletionRuleTests(TestCase):
    def setUp(self):
        User.objects.create_user(username='RITEL_DEMO_Teacher', is_instructor=True)
        self.student = User.objects.create_user(username='RITEL_DEMO_Student', is_student=True)
        self.output = tempfile.TemporaryDirectory(); self.addCleanup(self.output.cleanup)
        call_command('build_legacy_assessment_course',output=self.output.name)
        self.course = Course.objects.get(pk='cs0401-assessment-lab')
        self.instance = CourseInstance.objects.get(course=self.course)
        self.enrollment = Enrollment.objects.get(student=self.student,course_instance=self.instance)
        self.modules = list(self.course.units.first().modules.order_by('order'))

    def test_wrong_submission_completes_unlocks_and_retains_real_attempt_scores(self):
        first, second = self.modules[:2]
        progress = ModuleProgress.get_or_create_progress(user=self.student,module=first,course_instance=self.instance)[0]
        self.assertFalse(evaluate_module_access(second,self.enrollment).can_access)
        apply_progress_snapshot(progress,source='iframe',progress=1,is_complete=True,event_type='progress')
        self.assertFalse(progress.is_complete)
        self.assertFalse(evaluate_module_access(second,self.enrollment).can_access)
        for score in [0,100,0]:
            apply_progress_snapshot(progress,source='quizjet',score=max(progress.score or 0,score),
                success=score==100, progress=score/100,is_complete=score==100,event_type='outcome',
                payload={'attempt_score':score,'correct':score==100,'answer':str(score),'code':'example'})
            self.assertTrue(progress.is_complete)
            self.assertEqual(progress.progress,1)
        self.assertTrue(evaluate_module_access(second,self.enrollment).can_access)
        self.assertEqual(progress.score,100)
        self.assertEqual(list(progress.events.filter(event_type='outcome').order_by('id').values_list('score',flat=True)),[0,100,0])
        self.assertEqual(progress.events.filter(event_type='completion').count(),1)

    def test_pretest_unlocks_following_unit_only_after_all_ten_submissions(self):
        """Exercise the real QuizJET/PCRS outcome handlers with incorrect answers."""
        from modulearn.learning.services.quizjet_tracking import process_quizjet_response
        from modulearn.learning.services.pcrs_tracking import capture_pcrs_result_if_possible
        from modulearn.learning.selectors.courses import build_course_detail_context

        pretest = self.modules[0].unit
        target = Unit.objects.create(course=self.course, title='After pre-test', order=pretest.order + 1,
            is_locked=True, unlock_rule={'conditions': [{'type': 'previous_unit_completed'}]})
        activity = Module.objects.create(unit=target, title='Unlocked content', content_url='https://example.org/activity')
        self.client.force_login(self.student)
        launch = reverse('courses:launch_iframe_module', args=[self.instance.pk, activity.pk])
        self.assertEqual(len(self.modules), 10)
        self.assertFalse(evaluate_unit_access(target, self.enrollment).can_access)
        self.assertEqual(self.client.get(launch).status_code, 302)
        for index, module in enumerate(self.modules):
            self.assertEqual(module.completion_rule, 'submission')
            self.assertTrue(evaluate_module_access(module, self.enrollment).can_access)
            params = {'cid': self.course.pk, 'usr': self.student.username,
                      'course_instance_id': self.instance.pk, 'module_id': module.pk}
            request = RequestFactory().post('/submit', {'inputans': 'wrong', 'submission': 'incorrect code', 'svc': 'pretest'})
            request.user = self.student
            request.META['HTTP_REFERER'] = 'http://testserver/embed?' + urlencode(params)
            if module.provider_id == 'quizjet':
                response = HttpResponse('<iframe src="/um-vis-notificator/remote_update.html?action=actDone&amp;param=0"></iframe>', content_type='text/html')
                process_quizjet_response(request, 'adapt2.sis.pitt.edu', 'quizjet/EvaluateAnswer', response)
            else:
                response = HttpResponse(json.dumps({'score': 0, 'max_score': 1}), content_type='application/json')
                capture_pcrs_result_if_possible(request, 'pcrs.utm.utoronto.ca',
                    urlsplit(module.content_url).path.strip('/').replace('/embed', '/run'), response)
            progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=module)
            self.assertTrue(progress.is_complete)
            self.assertEqual(progress.attempts, 1)
            self.assertEqual(progress.score, 0)
            self.assertEqual(evaluate_unit_access(target, self.enrollment).can_access, index == 9)
            context = build_course_detail_context(self.student, self.instance)
            card = next(card for card in context['unit_cards'] if card['unit'].pk == pretest.pk)
            self.assertEqual(card['completed_count'], index + 1)
        self.assertEqual(self.client.get(launch).status_code, 200)
        other = CourseInstance.objects.create(course=self.course, group_name='Other session')
        other_enrollment = Enrollment.objects.create(student=self.student, course_instance=other)
        self.assertFalse(evaluate_unit_access(target, other_enrollment).can_access)

    def test_unit_roundtrip_remaps_dependencies_and_defaults_legacy_packages(self):
        other=Course.objects.create(id='copy',title='Copy')
        for phase in ['pretest','posttest']:
            payload=json.loads((Path(self.output.name)/f'{phase}-unit.json').read_text(encoding='utf-8'))
            import_unit(other,payload)
        for unit in other.units.all():
            previous=None
            for module in unit.modules.order_by('order'):
                self.assertEqual(module.completion_rule,'submission')
                self.assertTrue(module.allow_resubmission)
                self.assertEqual(module.is_locked,previous is not None)
                if previous:self.assertEqual(module.unlock_rule['conditions'][0]['target_id'],previous.pk)
                previous=module
        payload=json.loads((Path(self.output.name)/'pretest-unit.json').read_text(encoding='utf-8'))
        for activity in payload['unit']['modules']:
            activity.pop('completion_rule',None)
        legacy=Course.objects.create(id='legacy-copy',title='Legacy Copy')
        import_unit(legacy,payload)
        self.assertEqual(set(Module.objects.filter(unit__course=legacy).values_list('completion_rule',flat=True)),{'provider'})

    def test_opt_in_backfill_preserves_answers_scores_and_attempts(self):
        module=self.modules[0]
        module.completion_rule='provider';module.save()
        progress=ModuleProgress.get_or_create_progress(user=self.student,module=module,course_instance=self.instance)[0]
        apply_progress_snapshot(progress,source='quizjet',score=0,success=False,progress=0,is_complete=False,event_type='outcome',
            payload={'attempt_score':0,'correct':False,'answer':'wrong','code':'original'})
        progress.attempts=1;progress.save()
        original=progress.events.get(event_type='outcome')
        call_command('configure_legacy_assessment_completion',instance_id=self.instance.pk)
        progress.refresh_from_db();self.assertFalse(progress.is_complete)
        call_command('configure_legacy_assessment_completion',instance_id=self.instance.pk,apply=True)
        progress.refresh_from_db();self.assertTrue(progress.is_complete)
        self.assertEqual(progress.score,0);self.assertFalse(progress.success);self.assertEqual(progress.attempts,1)
        self.assertEqual(progress.completed_at,original.created_at)
        self.assertEqual(progress.events.get(pk=original.pk).payload['answer'],'wrong')
        call_command('configure_legacy_assessment_completion',instance_id=self.instance.pk,apply=True)
        self.assertEqual(progress.events.filter(source='completion_policy').count(),1)
