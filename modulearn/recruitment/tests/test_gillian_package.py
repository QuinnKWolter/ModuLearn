import json
from pathlib import Path
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from courses.models import Enrollment, Module, ModuleProgress
from recruitment.models import ParticipantSession
from recruitment.services.studies import create_study_for_instructor, export_study_to_json
from recruitment.services.flow import current_activity, advance_pending
from modulearn.learning.services.progress import apply_progress_snapshot


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class GillianPackageTests(TestCase):
    package_name = 'gillian-lab-study-2026-11-16.json'
    activity_count = 44
    condition_roles = {'practice':'practice', 'similar':'similar', 'matched':'matched'}
    initial_roles = ['consent', 'baseline']

    def test_package_import_roundtrip_and_all_condition_paths(self):
        data=json.loads((Path(__file__).resolve().parents[3]/'exports'/self.package_name).read_text(encoding='utf-8'))
        teacher=get_user_model().objects.create_user(username='gillian-researcher',is_instructor=True)
        study=create_study_for_instructor(teacher,title=data['study']['title'],template_data=data)
        self.assertTrue(study.participant_paced)
        self.assertTrue(study.retry_after_remediation)
        self.assertFalse(study.recruitment_sources.filter(is_active=True).exists())
        course=study.course_instance.course
        self.assertEqual(Module.objects.filter(unit__course=course).count(),self.activity_count)
        self.assertEqual(course.branch_rules.count(),24)
        clone=create_study_for_instructor(teacher,title='Roundtrip',template_data=export_study_to_json(study))
        self.assertEqual(clone.course_instance.course.branch_rules.count(),24)
        self.assertEqual(Module.objects.filter(unit__course=clone.course_instance.course,content_data__study_allow_next=True).count(),16)
        self.assertEqual(set(study.conditions.values_list('label', flat=True)), set(self.condition_roles))
        for label, intervention_role in self.condition_roles.items():
            student=get_user_model().objects.create_user(username='pilot-'+label,is_student=True,is_anonymous_participant=True)
            enrollment=Enrollment.objects.create(student=student,course_instance=study.course_instance)
            session=ParticipantSession.objects.create(user=student,enrollment=enrollment,recruitment_source=study.recruitment_sources.first(),external_pid=label,condition=label)
            def submit(module,correct):
                progress=ModuleProgress.objects.get(module=module,enrollment=enrollment)
                apply_progress_snapshot(progress,source='package_test',event_type='attempt',
                    score=100 if correct else 0,success=correct,progress=1 if correct else 0,is_complete=correct)
            roles=[]; mains=[]
            for _ in range(25):
                activity,state=current_activity(session,start_timer=True)
                if state['finished']: break
                role=activity.content_data['study_template_role'];roles.append(role)
                if role=='original':
                    mains.append(activity.content_data['study_item_id'])
                    submit(activity,False)
                    self.assertEqual(current_activity(session)[0],activity)
                    self.assertTrue(advance_pending(session,activity.pk))
                    target,_=current_activity(session)
                    self.assertEqual(target.content_data['study_template_role'],intervention_role)
                    self.assertEqual(target.content_data['study_template_slot'],activity.content_data['study_template_slot'])
                    if intervention_role=='matched': self.assertEqual(target.content_data['study_item_id'],activity.content_data['study_item_id'])
                    submit(target,intervention_role!='practice')
                    self.assertTrue(advance_pending(session,target.pk))
                    self.assertEqual(current_activity(session)[0],activity)
                submit(activity,role not in ['pretest','posttest'])
                if activity.module_type not in Module.FORM_LIKE_TYPES:
                    self.assertTrue(advance_pending(session,activity.pk))
            self.assertTrue(current_activity(session)[1]['finished'])
            self.assertEqual(mains,['Q11','Q12','M05','Q15','Q16','H05','H06','H07'])
            self.assertEqual(roles,self.initial_roles+['pretest']*4+['original']*8+['post_questionnaire']+['posttest']*4+['debrief'])


class GillianResearcherDraftPackageTests(GillianPackageTests):
    package_name = 'gillian-lab-study-2026-11-20.json'
    activity_count = 45
    condition_roles = {'more_practice':'practice', 'similar_example':'similar', 'matched_example':'matched'}
    initial_roles = ['consent', 'instructions', 'baseline']

    def test_content_revision_preserves_tested_exercises_and_imports_forms(self):
        root = Path(__file__).resolve().parents[3]/'exports'
        original = json.loads((root/'gillian-lab-study-2026-11-16.json').read_text(encoding='utf-8'))
        revised = json.loads((root/self.package_name).read_text(encoding='utf-8'))
        def exercises(data):
            return [m for u in data['course']['units'] for m in u['modules'] if m['module_type'] not in Module.FORM_LIKE_TYPES]
        self.assertTrue(exercises(original))
        self.assertEqual(exercises(original), exercises(revised))
        teacher = get_user_model().objects.create_user(username='draft-researcher', is_instructor=True)
        study = create_study_for_instructor(teacher, title='Draft content', template_data=revised)
        exported = export_study_to_json(study)
        expected = {m['title']: m for u in revised['course']['units'] for m in u['modules'] if 'form' in m}
        actual = {m['title']: m for u in exported['course']['units'] for m in u['modules'] if 'form' in m}
        self.assertEqual(set(expected), {'Consent', 'Instructions', 'Pretest', 'Post-study motivation questions', 'Debrief'})
        for title, module in expected.items():
            self.assertEqual(actual[title]['description'], module['description'])
            for field in ('instructions', 'submit_button_label', 'allow_resubmission', 'questions'):
                self.assertEqual(actual[title]['form'][field], module['form'][field])
        self.assertEqual(len(actual['Pretest']['form']['questions']), 6)
        self.assertEqual(len(actual['Post-study motivation questions']['form']['questions']), 15)
