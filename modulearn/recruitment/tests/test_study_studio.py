from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from courses.models import Enrollment, Module, ModuleBranchRule, ModuleProgress, ModuleProgressEvent, Unit
from modulearn.learning.services.progress import apply_progress_snapshot, record_module_launch
from recruitment.models import ParticipantSession, Study
from recruitment.services.flow import current_activity, allows_activity
from recruitment.services.studies import create_study_for_instructor, export_study_to_json


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class StudyStudioTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.teacher = User.objects.create_user(username='researcher', password='pass', is_instructor=True)
        self.student = User.objects.create_user(username='participant', is_student=True, is_anonymous_participant=True)
        self.study = create_study_for_instructor(self.teacher, title='Study', condition_labels='practice,similar,matched')
        self.course = self.study.course_instance.course
        self.course.units.all().delete()
        self.unit = Unit.objects.create(course=self.course, title='Learning', order=10)
        self.main = Module.objects.create(unit=self.unit, title='Question', order=1)
        self.next = Module.objects.create(unit=self.unit, title='Next', order=2)
        self.targets = {}
        for i, condition in enumerate(['practice', 'similar', 'matched']):
            module = Module.objects.create(unit=self.unit, title=condition, order=10+i, is_locked=True)
            ModuleBranchRule.objects.create(course=self.course, source_module=self.main, target_module=module,
                condition_type='failure', required_study_condition=condition)
            self.targets[condition] = module
        self.enrollment = Enrollment.objects.create(student=self.student, course_instance=self.study.course_instance)
        self.session = ParticipantSession.objects.create(recruitment_source=self.study.recruitment_sources.first(),
            user=self.student, enrollment=self.enrollment, external_pid='test', condition='similar')

    def attempt(self, module, correct):
        progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=module)
        apply_progress_snapshot(progress, source='test', event_type='attempt', score=100 if correct else 0,
            success=correct, progress=1 if correct else 0, is_complete=correct, payload={'test':True})
        return progress

    def test_wrong_routes_only_to_assigned_remediation_then_returns(self):
        self.assertEqual(current_activity(self.session)[0], self.main)
        self.attempt(self.main, False)
        self.assertEqual(current_activity(self.session)[0], self.targets['similar'])
        self.assertFalse(allows_activity(self.enrollment, self.targets['matched']))
        self.attempt(self.targets['similar'], True)
        self.assertEqual(current_activity(self.session)[0], self.main)
        self.attempt(self.main, True)
        self.assertEqual(current_activity(self.session)[0], self.next)
        self.attempt(self.next, True)
        self.assertTrue(current_activity(self.session)[1]['finished'])
        self.assertEqual(ModuleProgressEvent.objects.filter(event_type='study_transition').count(), 4)

    def test_each_condition_selects_its_own_branch(self):
        for label, target in self.targets.items():
            self.session.condition = label
            self.session.flow_state = {}
            self.session.save()
            ModuleProgress.objects.filter(enrollment=self.enrollment).update(study_condition=label)
            self.attempt(self.main, False)
            self.assertEqual(current_activity(self.session)[0], target)

    def test_correct_skips_remediation(self):
        self.attempt(self.main, True)
        self.assertEqual(current_activity(self.session)[0], self.next)

    def test_native_cupcake_wrong_attempt_routes_and_is_counted(self):
        from modulearn.learning.services.cupcake_tracking import record_cupcake_event
        from recruitment.services.study_analytics import build_study_analytics_context
        progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.main)
        envelope = {'event_id':'study-cupcake-check', 'message': {'type':'cupcake:log',
            'eventName':'answerChecked', 'activityType':'free-coding',
            'eventData':{'isCorrect':False, 'testCasesResults':[{'passed':True}, {'passed':False}]}}}
        record_cupcake_event(progress, envelope)
        record_cupcake_event(progress, envelope)  # Transport retry is not a second mistake.
        self.assertEqual(current_activity(self.session)[0], self.targets['similar'])
        self.assertEqual(progress.score, 50)
        participant = build_study_analytics_context(self.study)['participants'][0]
        self.assertEqual(participant['incorrect_attempts'], 1)
        self.assertEqual(participant['incorrect_activities'], 1)

    def test_proxy_access_uses_same_cursor_as_player(self):
        from modulearn.learning.services.access_rules import evaluate_module_access
        self.assertFalse(evaluate_module_access(self.next, self.enrollment).can_access)
        self.attempt(self.main, False)
        self.assertTrue(evaluate_module_access(self.targets['similar'], self.enrollment).can_access)
        self.assertFalse(evaluate_module_access(self.main, self.enrollment).can_access)

    def test_repeat_example_completion_can_return(self):
        self.attempt(self.main, False)
        self.attempt(self.targets['similar'], True)
        self.attempt(self.main, False)
        progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.targets['similar'])
        apply_progress_snapshot(progress, source='example', progress=1, success=True,
            is_complete=True, event_type='progress', payload={'viewed':True})
        self.assertEqual(current_activity(self.session)[0], self.main)

    def test_input_summary_and_preview_controls_are_private(self):
        from courses.models import ModuleForm, ModuleFormQuestion
        import json
        authored = ModuleForm.objects.create(module=self.main)
        question = ModuleFormQuestion.objects.create(form=authored, prompt='Code', question_type='long_answer')
        record_module_launch(ModuleProgress.objects.get(module=self.main, enrollment=self.enrollment))
        self.client.force_login(self.student)
        data = {'activity_id':self.main.pk, 'visit_id':'visit-1',
            'fields':{f'question_{question.pk}':{'keystrokes':12,'paste_count':1,'characters':15}}}
        response = self.client.post(reverse('recruitment:input_summary', args=[self.session.uuid]), {'summary':json.dumps(data)})
        self.assertEqual(response.status_code, 200)
        event = ModuleProgressEvent.objects.get(event_type='study_input')
        self.assertEqual(event.payload['fields'][f'question_{question.pk}']['paste_count'], 1)
        response = self.client.get(reverse('recruitment:flow_status', args=[self.session.uuid])+'?trace=1')
        self.assertIsNone(response.json()['trace'])

    def test_resource_acknowledgement_cannot_skip_scored_activity(self):
        self.client.force_login(self.student)
        record_module_launch(ModuleProgress.objects.get(module=self.main, enrollment=self.enrollment))
        url = reverse('recruitment:continue_resource', args=[self.session.uuid])
        self.assertEqual(self.client.post(url).status_code, 403)
        self.main.module_type = Module.MODULE_TYPE_FILE
        self.main.save(update_fields=['module_type'])
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(current_activity(self.session)[0], self.next)

    def test_condition_edit_updates_rules_and_invalid_edit_rolls_back(self):
        self.session.delete()
        self.enrollment.delete()
        self.client.force_login(self.teacher)
        payload = {'title':'Revised study', 'guided_flow':'on', 'assignment':'random'}
        for condition in self.study.conditions.all():
            payload.update({f'condition_{condition.pk}_label': 'example' if condition.label == 'similar' else condition.label,
                f'condition_{condition.pk}_name': condition.name, f'condition_{condition.pk}_active':'on'})
        response = self.client.post(reverse('recruitment:studio', args=[self.study.pk]), payload)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.course.branch_rules.filter(required_study_condition='example').exists())
        self.assertFalse(self.course.branch_rules.filter(required_study_condition='similar').exists())
        payload['title'] = 'Should roll back'
        payload[f'unit_{self.unit.pk}_seconds'] = '-1'
        self.client.post(reverse('recruitment:studio', args=[self.study.pk]), payload)
        self.study.refresh_from_db()
        self.assertEqual(self.study.title, 'Revised study')

    def test_remediation_failure_returns_without_recursing(self):
        self.attempt(self.main, False)
        self.attempt(self.targets['similar'], False)
        self.assertEqual(current_activity(self.session)[0], self.main)

    def test_late_callback_does_not_grade_or_reroute(self):
        self.attempt(self.main, False)
        self.attempt(self.main, True)
        self.assertEqual(current_activity(self.session)[0], self.targets['similar'])
        self.assertFalse(ModuleProgress.objects.get(enrollment=self.enrollment, module=self.main).is_complete)
        self.assertTrue(ModuleProgressEvent.objects.filter(event_type='study_late_event').exists())

    def test_timer_persists_and_skips_section_without_fabricating_credit(self):
        self.unit.time_limit_seconds = 30
        self.unit.save()
        later = Unit.objects.create(course=self.course, title='Posttest', order=20)
        posttest = Module.objects.create(unit=later, title='Posttest')
        now = timezone.now()
        with patch('recruitment.services.flow.timezone.now', return_value=now):
            _, first = current_activity(self.session, start_timer=True)
        with patch('recruitment.services.flow.timezone.now', return_value=now + timedelta(seconds=15)):
            _, again = current_activity(self.session, start_timer=True)
        self.assertEqual(first['deadlines'], again['deadlines'])
        self.attempt(self.main, False)
        with patch('recruitment.services.flow.timezone.now', return_value=now + timedelta(seconds=31)):
            self.assertEqual(current_activity(self.session)[0], posttest)
        self.assertFalse(ModuleProgress.objects.get(enrollment=self.enrollment, module=self.main).is_complete)

    def test_hidden_main_is_not_shown(self):
        self.main.is_visible = False
        self.main.save()
        self.assertEqual(current_activity(self.session)[0], self.next)

    def test_finished_section_is_not_later_reported_as_timed_out(self):
        self.unit.time_limit_seconds = 30
        self.unit.save()
        later = Unit.objects.create(course=self.course, title='Later', order=20)
        Module.objects.create(unit=later, title='Later question')
        now = timezone.now()
        with patch('recruitment.services.flow.timezone.now', return_value=now):
            current_activity(self.session, start_timer=True)
            self.attempt(self.main, True)
            self.attempt(self.next, True)
        with patch('recruitment.services.flow.timezone.now', return_value=now + timedelta(seconds=60)):
            _, state = current_activity(self.session)
        self.assertNotIn(self.unit.pk, state['expired_units'])

    def test_cannot_claim_completion_early(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('recruitment:complete', args=[self.session.uuid])+'?outcome=completed')
        self.assertRedirects(response, reverse('recruitment:resume_session', args=[self.session.uuid]), fetch_redirect_response=False)
        self.session.refresh_from_db()
        self.assertFalse(self.session.is_finished)

    def test_status_is_private(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse('recruitment:flow_status', args=[self.session.uuid])).status_code, 404)

    def test_real_participant_cannot_simulate(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(reverse('recruitment:simulate', args=[self.session.uuid]), {'result':'correct'}).status_code, 404)

    def test_preview_is_separate_and_exit_restores_researcher(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('recruitment:preview', args=[self.study.pk]), {'condition':'matched'})
        self.assertEqual(response.status_code, 302)
        clone = Study.objects.get(preview_of=self.study)
        run = ParticipantSession.objects.get(recruitment_source__study=clone)
        self.assertEqual(run.condition, 'matched')
        self.assertNotEqual(run.user, self.teacher)
        self.assertFalse(clone.recruitment_sources.filter(is_active=True).exists())
        self.assertEqual(ParticipantSession.objects.filter(recruitment_source__study=self.study).count(), 1)
        self.assertEqual(self.client.get(response.url).status_code, 302)
        response = self.client.post(reverse('recruitment:exit_preview'))
        self.assertRedirects(response, reverse('recruitment:studio', args=[self.study.pk]), fetch_redirect_response=False)
        self.assertFalse(Study.objects.filter(pk=clone.pk).exists())
        self.assertEqual(int(self.client.session['_auth_user_id']), self.teacher.pk)

    def test_template_roundtrip_preserves_timer_and_conditions(self):
        self.unit.time_limit_seconds = 120
        self.unit.save()
        condition = self.study.conditions.get(label='matched')
        condition.name = 'Matched Examples'
        condition.description = 'Original problem, explained line by line.'
        condition.save()
        clone = create_study_for_instructor(self.teacher, title='Clone', template_data=export_study_to_json(self.study))
        self.assertTrue(clone.guided_flow)
        self.assertEqual(clone.course_instance.course.units.first().time_limit_seconds, 120)
        self.assertEqual(clone.conditions.get(label='matched').description, condition.description)
        self.assertEqual(clone.course_instance.course.branch_rules.count(), 3)
        self.assertFalse(clone.course_instance.course.branch_rules.filter(source_module__unit__course=self.course).exists())

    def test_editor_private_and_locked_after_entry(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('recruitment:studio', args=[self.study.pk])).status_code, 403)
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse('recruitment:studio', args=[self.study.pk])).status_code, 200)
        self.client.post(reverse('recruitment:studio', args=[self.study.pk]), {'title':'Changed'})
        self.study.refresh_from_db()
        self.assertEqual(self.study.title, 'Study')

    def test_markdown_escapes_html_and_code(self):
        from courses.templatetags.study_text import study_markdown
        value = study_markdown('**Important**\n<script>alert(1)</script>\n```python\n<img src=x>\n```')
        self.assertIn('<strong>Important</strong>', value)
        self.assertNotIn('<script>', value)
        self.assertNotIn('<img', value)
        self.assertIn('&lt;script&gt;', value)

    def test_random_assignment_uses_random_choice(self):
        from recruitment.services.conditions import assign_condition
        with patch('recruitment.services.conditions.secrets.choice', return_value='matched') as choose:
            self.assertEqual(assign_condition(self.study.recruitment_sources.first(), 'person'), 'matched')
            choose.assert_called_once()

    def test_events_export_contains_transitions(self):
        self.attempt(self.main, False)
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('recruitment:events_csv', args=[self.study.pk]))
        content = b''.join(response.streaming_content).decode()
        self.assertIn('incorrect_remediation', content)
        self.assertIn('study_transition', content)

    def test_content_only_shell_for_participants_and_finished_previews(self):
        from django.test import RequestFactory
        from django.template.loader import render_to_string
        from recruitment.context_processors import study_player
        request = RequestFactory().get('/')
        request.user = self.student
        request.session = {}
        context = study_player(request)
        self.assertTrue(context['study_shell'])
        self.assertFalse(context['study_preview'])
        for template in ['base.html', 'content_base.html']:
            html = render_to_string(template, context, request=request)
            self.assertNotIn('footer-shell', html)
            self.assertNotIn('shell-background', html)
            self.assertNotIn('data-study-timer', html)
            self.assertNotIn('Study in progress', html)
            self.assertNotIn('Test A Branch', html)
            self.assertNotIn('class="study-exit"', html)
        original = create_study_for_instructor(self.teacher, title='Original')
        self.study.preview_of = original
        self.study.save(update_fields=['preview_of'])
        self.session.status = 'completed'
        self.session.save(update_fields=['status'])
        context = study_player(request)
        self.assertTrue(context['study_preview'])
        self.assertNotIn('study_player', context)
        html = render_to_string('recruitment/preview_finished.html', context, request=request)
        self.assertIn('class="study-exit"', html)
        self.assertNotIn('footer-shell', html)
        self.assertNotIn('study-player-config', html)
