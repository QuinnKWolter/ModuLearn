from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from courses.models import Module, ModuleProgress, ModuleProgressEvent
from recruitment.services.flow import current_activity, advance_pending, allows_activity
from recruitment.services.studies import export_study_to_json, create_study_for_instructor
from .test_study_studio import StudyStudioTests


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ParticipantPacingTests(TestCase):
    attempt = StudyStudioTests.attempt

    def test_copy_condition_connections_preserves_variants_and_is_repeatable(self):
        from courses.models import ModuleBranchRule
        self.session.delete()  # Protocol editing is deliberately locked with real participants.
        self.client.force_login(self.teacher)
        for score in [40, 75]:
            ModuleBranchRule.objects.create(course=self.course, source_module=self.main,
                target_module=self.targets['practice'], condition_type='score_lt',
                threshold=score, priority=2, required_study_condition='practice')
        source_ids=set(self.course.branch_rules.filter(required_study_condition='practice').values_list('id',flat=True))
        original_target_ids=set(self.course.branch_rules.filter(required_study_condition='matched').values_list('id',flat=True))
        for _ in range(2):
            response=self.client.post(reverse('recruitment:studio',args=[self.study.pk]),
                {'action':'copy_rules','from_condition':'practice','to_condition':'matched'})
            self.assertEqual(response.status_code,302)
        copied=self.course.branch_rules.filter(required_study_condition='matched')
        self.assertEqual(copied.count(),len(original_target_ids)+len(source_ids))
        self.assertEqual(set(copied.filter(condition_type='score_lt').values_list('threshold',flat=True)),{40,75})
        self.assertTrue(original_target_ids.issubset(set(copied.values_list('id',flat=True))))
        self.assertEqual(source_ids,set(self.course.branch_rules.filter(required_study_condition='practice').values_list('id',flat=True)))

    def test_complete_activity_preview_uses_unsaved_content_without_submitting(self):
        import json
        from courses.models import ModuleFormSubmission
        self.client.force_login(self.teacher)
        questions = [dict(prompt='**Question**', help='Helpful *hint*', type=kind,
                          options=['First', 'Second'], required=True, low='Low', high='High')
                     for kind in ['short_answer', 'long_answer', 'single_choice', 'multiple_choice', 'likert']]
        data = dict(title='Unsaved title <script>', description='# Description', instructions='Instructions',
                    continuation='Continue to next', isForm=True, questions=questions)
        before = ModuleFormSubmission.objects.count()
        response = self.client.post(reverse('recruitment:text_preview'), {'activity': json.dumps(data)})
        self.assertEqual(response.status_code, 200)
        html = response.json()['html']
        for text in ['Unsaved title &lt;script&gt;', '<h1>Description</h1>', 'Instructions',
                     '<strong>Question</strong>', '<em>hint</em>', 'Continue to next', 'Low', 'High']:
            self.assertIn(text, html)
        self.assertEqual(html.count('<fieldset'), 5)
        self.assertEqual(html.count('type="checkbox"'), 2)
        self.assertEqual(html.count('type="radio"'), 7)
        self.assertNotIn('type="submit"', html)
        self.assertNotIn('<form', html)
        self.assertEqual(ModuleFormSubmission.objects.count(), before)
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(reverse('recruitment:text_preview'), {'activity': json.dumps(data)}).status_code, 403)

    def test_activity_preview_rejects_invalid_or_unbounded_payloads(self):
        import json
        self.client.force_login(self.teacher)
        for data in ['not JSON', '[]', json.dumps({'questions': [None]}),
                     json.dumps({'description': '<x>' * 17000}),
                     json.dumps({'questions': [{'type': 'unknown'}]}),
                     json.dumps({'questions': [{}] * 201})]:
            with self.subTest(data=data[:50]):
                self.assertEqual(self.client.post(reverse('recruitment:text_preview'), {'activity': data}).status_code, 400)

    def setUp(self):
        StudyStudioTests.setUp(self)
        self.study.participant_paced = True
        self.study.save(update_fields=['participant_paced'])
        self.client.force_login(self.student)

    def test_feedback_waits_and_duplicate_completion_does_not_change_branch(self):
        self.attempt(self.main, False)
        current, state = current_activity(self.session)
        self.assertEqual(current, self.main)
        self.assertEqual(state['pending_transition']['to'], self.targets['similar'].pk)
        self.assertTrue(allows_activity(self.enrollment, self.main))
        self.assertFalse(allows_activity(self.enrollment, self.targets['similar']))
        self.assertTrue(advance_pending(self.session, self.main.pk))
        self.assertFalse(advance_pending(self.session, self.main.pk))
        self.attempt(self.targets['similar'], True)
        self.assertEqual(current_activity(self.session)[0], self.targets['similar'])
        self.assertTrue(advance_pending(self.session, self.targets['similar'].pk))
        self.assertEqual(current_activity(self.session)[0], self.main)

    def test_next_cannot_skip_an_unattempted_problem_or_advance_twice(self):
        url=reverse('recruitment:continue_resource',args=[self.session.uuid])
        self.assertEqual(self.client.post(url,{'activity_id':self.main.pk}).status_code,403)
        self.attempt(self.main, True)
        self.assertEqual(self.client.post(url,{'activity_id':self.main.pk}).status_code,302)
        self.assertEqual(self.client.post(url,{'activity_id':self.main.pk}).status_code,409)
        self.assertEqual(current_activity(self.session)[0],self.next)

    def test_new_submission_before_next_replaces_pending_destination(self):
        self.attempt(self.main,False)
        self.attempt(self.main,True)
        self.assertTrue(advance_pending(self.session,self.main.pk))
        self.assertEqual(current_activity(self.session)[0],self.next)

    def test_markdown_preview_is_private_and_uses_safe_participant_renderer(self):
        url=reverse('recruitment:text_preview')
        self.assertEqual(self.client.post(url,{'text':'**hello**'}).status_code,403)
        self.client.force_login(self.teacher)
        response=self.client.post(url,{'text':'**hello**\n<script>alert(1)</script>'})
        self.assertEqual(response.status_code,200)
        self.assertIn('<strong>hello</strong>',response.json()['html'])
        self.assertNotIn('<script>',response.json()['html'])

    def test_form_preview_batch_preserves_order_escapes_html_and_limits_size(self):
        self.client.force_login(self.teacher)
        url = reverse('recruitment:text_preview')
        response = self.client.post(url, {'texts': ['# Heading', '**Question**', '<script>bad()</script>', '']})
        self.assertEqual(response.json()['html'], ['<h1>Heading</h1>\n', '<p><strong>Question</strong></p>\n', '<p>&lt;script&gt;bad()&lt;/script&gt;</p>\n', ''])
        self.assertEqual(self.client.post(url, {'texts': ['a'] * 501}).status_code, 400)
        self.assertEqual(self.client.post(url, {'texts': ['a' * 50001]}).status_code, 400)

    def test_example_acknowledgement_logs_completion_without_a_score(self):
        from modulearn.learning.services.progress import record_module_launch
        example=self.targets['similar']
        example.module_type=Module.MODULE_TYPE_SPLICE_SMART_CONTENT
        example.content_data={'study_allow_next':True}
        example.save()
        self.attempt(self.main,False)
        advance_pending(self.session,self.main.pk)
        progress=ModuleProgress.objects.get(enrollment=self.enrollment,module=example)
        record_module_launch(progress)
        url=reverse('recruitment:continue_resource',args=[self.session.uuid])
        self.assertEqual(self.client.post(url,{'activity_id':example.pk}).status_code,302)
        self.assertEqual(current_activity(self.session)[0],self.main)
        progress.refresh_from_db()
        self.assertTrue(progress.is_complete)
        self.assertIsNone(progress.score)
        self.assertEqual(progress.attempts,0)

    def test_wrong_pretest_submission_can_advance_without_claiming_correctness(self):
        self.course.branch_rules.filter(source_module=self.main).delete()
        self.main.completion_rule=Module.COMPLETION_SUBMISSION
        self.main.save()
        self.attempt(self.main,False)
        self.assertTrue(advance_pending(self.session,self.main.pk))
        self.assertEqual(current_activity(self.session)[0],self.next)
        self.assertFalse(ModuleProgress.objects.get(enrollment=self.enrollment,module=self.main).success)

    def test_untimed_visit_includes_feedback_review_duration(self):
        now=timezone.now()
        with patch('recruitment.services.flow.timezone.now',return_value=now):
            current_activity(self.session,start_timer=True)
        self.attempt(self.main,True)
        with patch('recruitment.services.flow.timezone.now',return_value=now+timedelta(seconds=95)):
            advance_pending(self.session,self.main.pk)
        event=ModuleProgressEvent.objects.get(event_type='study_transition')
        self.assertEqual(event.payload['elapsed_seconds'],95)
        self.assertEqual(current_activity(self.session)[1]['deadlines'],{})

    def test_expired_section_cannot_be_advanced_using_old_pending_next(self):
        self.unit.time_limit_seconds=10
        self.unit.save()
        now=timezone.now()
        with patch('recruitment.services.flow.timezone.now',return_value=now):
            current_activity(self.session,start_timer=True)
            self.attempt(self.main,False)
        with patch('recruitment.services.flow.timezone.now',return_value=now+timedelta(seconds=11)):
            self.assertFalse(advance_pending(self.session,self.main.pk))
        self.assertTrue(current_activity(self.session)[1]['finished'])

    def test_edit_connection_and_reject_foreign_target_atomically(self):
        from django.test import RequestFactory
        from courses.views import _update_branching_rules
        from courses.models import ModuleBranchRule, Unit
        rules=list(self.course.branch_rules.order_by('id'))
        rule=rules[0]
        data={f'branch_rule_{r.pk}_active':'on' for r in rules}
        prefix=f'branch_rule_{rule.pk}'
        data.update({prefix+'_source':self.next.pk,prefix+'_target':self.targets['matched'].pk,
            prefix+'_condition':'score_lt',prefix+'_threshold':'45',prefix+'_required_study_condition':'practice'})
        _update_branching_rules(RequestFactory().post('/',data),self.course)
        rule.refresh_from_db()
        self.assertEqual(rule.source_module,self.next)
        self.assertEqual(rule.target_module,self.targets['matched'])
        self.assertEqual(rule.threshold,45)
        self.assertEqual(rule.required_study_condition,'practice')
        clone=create_study_for_instructor(self.teacher,title='Other study')
        foreign=Module.objects.filter(unit__course=clone.course_instance.course).first()
        second=rules[1]; p=f'branch_rule_{second.pk}'
        data.update({prefix+'_threshold':'65',p+'_source':self.main.pk,p+'_target':foreign.pk,p+'_condition':'failure'})
        with self.assertRaises(ValueError):
            _update_branching_rules(RequestFactory().post('/',data),self.course)
        rule.refresh_from_db()
        self.assertEqual(rule.threshold,45)

    def test_retry_setting_and_pacing_roundtrip(self):
        self.study.retry_after_remediation=False
        self.study.save()
        self.attempt(self.main,False)
        advance_pending(self.session,self.main.pk)
        self.attempt(self.targets['similar'],False)
        advance_pending(self.session,self.targets['similar'].pk)
        self.assertEqual(current_activity(self.session)[0],self.next)
        clone=create_study_for_instructor(self.teacher,title='Clone',template_data=export_study_to_json(self.study))
        self.assertTrue(clone.participant_paced)
        self.assertFalse(clone.retry_after_remediation)
