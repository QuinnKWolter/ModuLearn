import json
import tempfile
from pathlib import Path
from django.test import TestCase, RequestFactory, override_settings
from django.core.management import call_command, CommandError
from accounts.models import User
from courses.models import Course, CourseInstance, Enrollment, Module, ModuleProgress, ModuleFormSubmission
from courses.surveys import handle_survey
from modulearn.learning.services.unit_packages import import_unit


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class SurveyTests(TestCase):
    def setUp(self):
        self.files = tempfile.TemporaryDirectory()
        self.addCleanup(self.files.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.files.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.user = User.objects.create_user(username='survey_student', is_student=True)
        self.course = Course.objects.create(id='survey', title='Survey Lab')
        self.instance = CourseInstance.objects.create(course=self.course, group_name='Survey')
        self.enrollment = Enrollment.objects.create(student=self.user, course_instance=self.instance)
        call_command('build_legacy_survey_units', instance_id=self.instance.pk, output=self.files.name, verbosity=0)
        self.module = Module.objects.get(unit__course=self.course, title='Pre-Survey')
        self.progress = ModuleProgress.get_or_create_progress(user=self.user, module=self.module, course_instance=self.instance)[0]

    def request(self, data=None):
        factory = RequestFactory()
        request = factory.get('/survey') if data is None else factory.post('/survey', data)
        request.user = self.user
        response = handle_survey(request, self.instance, self.module, self.progress, False)
        self.progress.refresh_from_db()
        return response

    def answer(self, **overrides):
        draft = self.progress.state_data['survey_draft']
        page = next(p for p in self.module.content_data['survey']['pages'] if p['id'] == draft['order'][draft['index']])
        data = {'page_token': draft['token'], 'action': 'next'}
        data.update({r['key']: r['options'][0]['id'] for r in page['rows']})
        data.update(overrides)
        return self.request(data)

    def test_full_survey_is_ungraded_and_records_all_rows_once(self):
        self.request()
        while not self.progress.state_data['survey_draft'].get('finished'):
            self.assertEqual(self.answer().status_code, 302)
        self.assertTrue(self.progress.is_complete)
        self.assertEqual(self.progress.progress, 1)
        self.assertIsNone(self.progress.score)
        self.assertEqual(self.progress.attempts, 1)
        submission = ModuleFormSubmission.objects.get(enrollment=self.enrollment)
        self.assertEqual(submission.answers.count(), 39)
        self.assertTrue(all(a.value['saved_at'] and a.value['codes'] for a in submission.answers.all()))
        self.request({'page_token':'duplicate'})
        self.assertEqual(ModuleFormSubmission.objects.count(), 1)
        self.assertEqual(self.progress.events.filter(source='native_survey', event_type='study_input').count(), 16)

    def test_required_invalid_stale_and_resume(self):
        self.request()
        token = self.progress.state_data['survey_draft']['token']
        self.assertContains(self.request({'page_token':token}), 'Please answer every item')
        self.assertContains(self.answer(QID35='999'), 'valid response')
        self.answer()
        self.assertContains(self.request({'page_token':token}), 'already changed')
        self.request()
        self.assertEqual(self.progress.state_data['survey_draft']['index'], 1)
        self.answer(action='back')
        self.assertEqual(self.progress.state_data['survey_draft']['index'], 0)
        self.assertContains(self.request(), 'checked')

    def test_decline_stops_without_completion(self):
        self.request()
        self.answer(QID35='4')
        self.assertContains(self.request(), 'declined participation')
        self.assertFalse(self.progress.is_complete)
        submission = ModuleFormSubmission.objects.get()
        self.assertFalse(submission.is_complete)
        self.assertEqual(submission.answers.count(), 1)

    def test_matrix_validation_multiselect_and_text_entry(self):
        self.request()
        while self.progress.state_data['survey_draft']['order'][self.progress.state_data['survey_draft']['index']] != 'QID12':
            draft = self.progress.state_data['survey_draft']
            if draft['order'][draft['index']] in ('QID29', 'QID33'):
                response = self.request({'page_token': draft['token']})
                self.assertContains(response, 'Please answer every item')
                self.assertFalse(self.progress.is_complete)
            self.answer()
        self.answer(QID12='3', QID12_text_3='Local test self-description')
        self.answer()
        self.answer(QID52=['1', '3'], QID52_text_3='Local test ethnicity')
        while not self.progress.state_data['survey_draft'].get('finished'):
            self.answer()
        answers = {a.value['question_id']: a for a in ModuleFormSubmission.objects.get().answers.all()}
        self.assertEqual(answers['QID12'].value['text']['3'], 'Local test self-description')
        self.assertEqual(answers['QID52'].value['codes'], ['1', '3'])
        self.assertEqual(answers['QID52'].value['text']['3'], 'Local test ethnicity')

    def test_export_import_and_post_completion(self):
        other = Course.objects.create(id='reused-surveys', title='Reused')
        for phase, count in [('pre',39), ('post',6)]:
            payload = json.loads((Path(self.files.name)/f'{phase}-survey-unit.json').read_text(encoding='utf-8'))
            import_unit(other, payload)
            module = Module.objects.get(unit__course=other, title=f'{phase.title()}-Survey')
            self.assertEqual(module.form.questions.count(), count)
            self.assertFalse(module.is_graded)
            self.assertEqual(sum(len(p['rows']) for p in module.content_data['survey']['pages']), count)
            if phase == 'pre':
                with module.content_file.open('rb') as stream:self.assertTrue(stream.read().startswith(b'%PDF'))
        self.module = Module.objects.get(unit__course=self.course, title='Post-Survey')
        self.progress = ModuleProgress.get_or_create_progress(user=self.user, module=self.module, course_instance=self.instance)[0]
        self.request()
        while not self.progress.state_data['survey_draft'].get('finished'):self.answer()
        self.assertEqual(ModuleFormSubmission.objects.get().answers.count(),6)
        with self.assertRaises(CommandError):
            call_command('build_legacy_survey_units', instance_id=self.instance.pk, output=self.files.name)
