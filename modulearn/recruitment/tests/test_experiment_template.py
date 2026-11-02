import json
from pathlib import Path
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from courses.models import Enrollment, Module, ModuleProgress
from recruitment.models import ParticipantSession
from recruitment.services.studies import create_study_for_instructor, export_study_to_json
from recruitment.services.flow import current_activity
from modulearn.learning.services.progress import apply_progress_snapshot


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ExperimentTemplateTests(TestCase):
    def test_import_roundtrip_and_all_24_condition_branches(self):
        template = json.loads((Path(__file__).resolve().parents[3] / 'exports' / 'python-remediation-study-template.json').read_text(encoding='utf-8'))
        teacher = get_user_model().objects.create_user(username='template-researcher', is_instructor=True)
        study = create_study_for_instructor(teacher, title=template['study']['title'], template_data=template)
        course = study.course_instance.course
        self.assertEqual(course.branch_rules.count(), 24)
        self.assertEqual(Module.objects.filter(unit__course=course).count(), 38)
        self.assertEqual(set(study.conditions.values_list('label', flat=True)), {'practice', 'similar', 'matched'})
        self.assertFalse(study.recruitment_sources.filter(is_active=True).exists())
        self.assertEqual(study.recruitment_sources.get().condition_strategy, 'random')
        final = Module.objects.get(unit__course=course, content_data__study_template_role='transfer_test')
        self.assertTrue(final.content_data['study_shuffle_questions'])
        self.assertEqual(final.form.questions.count(), 2)
        originals = list(Module.objects.filter(unit__course=course, content_data__study_template_role='original').order_by('order'))
        practice = list(Module.objects.filter(unit__course=course, content_data__study_template_role='practice').order_by('order'))
        for index, (original, target) in enumerate(zip(originals, practice)):
            original_key = f'free_coding_q{index+9:02d}'
            practice_key = f'free_coding_{"m" if index < 4 else "h"}{index%4+1:02d}'
            for module, key in [(original, original_key), (target, practice_key)]:
                self.assertEqual(module.content_url, f'https://adapt2.sis.pitt.edu/cupcake/#/activities/gillian-python/{key}.yaml?protocol=splice')
                self.assertEqual(module.content_data['study_item_id'], key)
                self.assertTrue(module.content_data['catalog_id'])
                self.assertNotIn('source_code', module.content_data)
            self.assertTrue(course.branch_rules.filter(source_module=original, target_module=target, required_study_condition='practice').exists())
        self.assertEqual(Module.objects.filter(unit__course=course, content_data__study_template_role__in=['similar','matched'], content_data__requires_material_replacement=True).count(), 16)
        exported = export_study_to_json(study)
        clone = create_study_for_instructor(teacher, title='Roundtrip', template_data=exported)
        self.assertEqual(clone.course_instance.course.branch_rules.count(), 24)
        self.assertTrue(clone.guided_flow)
        for condition in ['practice', 'similar', 'matched']:
            user = get_user_model().objects.create_user(username='template-'+condition, is_student=True, is_anonymous_participant=True)
            enrollment = Enrollment.objects.create(student=user, course_instance=study.course_instance)
            session = ParticipantSession.objects.create(user=user, enrollment=enrollment, recruitment_source=study.recruitment_sources.get(), external_pid=condition, condition=condition)
            visited = []
            branches = 0
            def submit(module, correct):
                progress = ModuleProgress.objects.get(enrollment=enrollment, module=module)
                apply_progress_snapshot(progress, source='template_test', event_type='attempt', score=100 if correct else 0,
                    success=correct, progress=1 if correct else 0, is_complete=correct, payload={'test': True})
            for _ in range(20):
                module, state = current_activity(session)
                if state['finished']:
                    break
                visited.append(module.content_data['study_template_role'])
                if module.content_data['study_template_role'] == 'original':
                    submit(module, False)
                    target, _ = current_activity(session)
                    self.assertEqual(target.content_data['study_template_role'], condition)
                    self.assertEqual(target.content_data['study_template_slot'], module.content_data['study_template_slot'])
                    # Incorrect additional practice still returns to the original.
                    submit(target, condition != 'practice')
                    self.assertEqual(current_activity(session)[0], module)
                    branches += 1
                submit(module, True)
            self.assertTrue(current_activity(session)[1]['finished'])
            self.assertEqual(branches, 8)
            self.assertEqual(visited, ['consent', 'baseline', 'pretest'] + ['original']*8 + ['post_questionnaire', 'transfer_test', 'debrief'])
