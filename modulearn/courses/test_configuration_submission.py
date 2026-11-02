import json
import tempfile
from unittest.mock import patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from courses.models import (Course, CourseInstance, CourseProgress, Enrollment,
                            Module, ModuleBranchRule, ModuleProgress, ModuleProgressEvent, Unit)


@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
                            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}})
class ConfigurationSubmissionTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='config-teacher', is_instructor=True)
        self.course = Course.objects.create(id='large-config', title='Configuration')
        self.course.instructors.add(self.teacher)
        self.instance = CourseInstance.objects.create(course=self.course, group_name='Configuration')
        self.instance.instructors.add(self.teacher)
        self.unit = Unit.objects.create(course=self.course, title='Original unit', order=1)
        self.first = Module.objects.create(unit=self.unit, title='First', order=1, content_url='https://example.org/first')
        self.second = Module.objects.create(unit=self.unit, title='Second', order=2)
        self.url = reverse('courses:course_configuration', args=[self.instance.pk])
        self.client.force_login(self.teacher)

    def fields(self):
        fields = [(f'unit_{unit.pk}_visible', '1') for unit in self.course.units.all()]
        for module in Module.objects.filter(unit__course=self.course, is_recommendation_only=False):
            fields.extend([
                (f'module_{module.pk}_title', module.title),
                (f'module_{module.pk}_order', str(module.order)),
                (f'module_{module.pk}_visible', '1'),
                (f'module_{module.pk}_unit_id', str(module.unit_id)),
            ])
        return dict(fields)

    def post(self, fields, **extra):
        return self.client.post(self.url, {
            'action': 'update_structure', 'structure_controls': json.dumps(list(fields.items())), **extra,
        })

    def test_large_course_can_reorder_and_hide_without_raising_global_field_limit(self):
        Module.objects.bulk_create([
            Module(unit=self.unit, title=f'Extra {i}', order=i + 3) for i in range(262)
        ])
        fields = self.fields()
        self.assertGreater(len(fields), settings.DATA_UPLOAD_MAX_NUMBER_FIELDS)
        fields[f'module_{self.first.pk}_order'] = '2'
        fields[f'module_{self.second.pk}_order'] = '1'
        fields[f'module_{self.first.pk}_visible'] = '0'
        response = self.post(fields)
        self.assertRedirects(response, self.url)
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual(self.first.order, 2)
        self.assertEqual(self.second.order, 1)
        self.assertFalse(self.first.is_visible)
        self.assertTrue(self.second.is_visible)
        self.assertEqual(self.first.content_url, 'https://example.org/first')
        self.assertEqual(self.unit.modules.filter(is_visible=True).count(), 263)

    def test_failed_save_rolls_back_prior_edits_and_deletions(self):
        fields = self.fields()
        fields[f'unit_{self.unit.pk}_title'] = 'Should roll back'
        fields[f'module_{self.first.pk}_delete'] = '1'
        fields[f'module_{self.second.pk}_order'] = 'invalid'
        response = self.post(fields)
        self.assertRedirects(response, self.url)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.title, 'Original unit')
        self.assertTrue(Module.objects.filter(pk=self.first.pk).exists())

    def test_packed_controls_preserve_file_uploads(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.post(self.fields(), **{
                f'module_{self.first.pk}_content_file': SimpleUploadedFile('example.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
            })
            self.assertEqual(response.status_code, 302)
            self.first.refresh_from_db()
            with self.first.content_file.open('rb') as uploaded:
                self.assertEqual(uploaded.read(), b'%PDF-1.4 test')

    def test_malformed_payload_does_not_change_configuration(self):
        for packed in ('{', '{}', '[["action", "delete"]]', '[["module_1_title", null]]'):
            with self.subTest(packed=packed):
                response = self.client.post(self.url, {'action': 'update_structure', 'structure_controls': packed})
                self.assertRedirects(response, self.url)
                self.first.refresh_from_db()
                self.assertTrue(self.first.is_visible)
                self.assertEqual(self.first.title, 'First')

    def test_student_cannot_save_packed_configuration(self):
        self.client.force_login(User.objects.create_user(username='config-student'))
        self.assertEqual(self.post(self.fields()).status_code, 403)

    def test_packed_submission_still_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.teacher)
        data = {'action': 'update_structure', 'structure_controls': json.dumps(list(self.fields().items()))}
        self.assertEqual(client.post(self.url, data).status_code, 403)
        client.get(self.url)
        data['csrfmiddlewaretoken'] = client.cookies['csrftoken'].value
        self.assertEqual(client.post(self.url, data).status_code, 302)

    def test_delete_unit_removes_contents_and_refreshes_all_sessions(self):
        from modulearn.learning.services.progress import apply_progress_snapshot
        from modulearn.learning.services.grading import refresh_course_grades

        keep = Unit.objects.create(course=self.course, title='Keep', order=2)
        activity = Module.objects.create(unit=keep, title='Keep completed activity')
        hidden = Module.objects.create(unit=self.unit, title='Recommendation only', is_recommendation_only=True)
        branch = ModuleBranchRule.objects.create(course=self.course, source_module=self.first,
            target_module=activity, condition_type='completed')
        other = CourseInstance.objects.create(course=self.course, group_name='Other session')
        student = User.objects.create_user(username='unit-delete-student')
        enrollments = [Enrollment.objects.create(student=student, course_instance=instance)
                       for instance in (self.instance, other)]
        preserved_progress_ids = []
        for enrollment in enrollments:
            for module in (activity, self.first):
                progress = ModuleProgress.objects.get(module=module, enrollment=enrollment)
                apply_progress_snapshot(progress, source='test', progress=1, score=100, success=True)
                if module == activity:
                    preserved_progress_ids.append(progress.pk)
        for instance in (self.instance, other):
            instance.grading_policy = {
                'units': {str(self.unit.pk): {'weight': 2}, str(keep.pk): {'weight': 1}},
                'groups': [{'unit_ids': [str(self.unit.pk)], 'deduction': 5},
                           {'unit_ids': [str(self.unit.pk), str(keep.pk)], 'deduction': 2}],
            }
            instance.save(update_fields=['grading_policy'])
        refresh_course_grades(self.course)
        self.assertEqual(CourseProgress.objects.get(enrollment=enrollments[0]).total_modules, 3)
        fields = self.fields()
        fields[f'unit_{self.unit.pk}_delete'] = '1'
        fields[f'module_{activity.pk}_locked'] = '1'
        fields[f'module_{activity.pk}_rule_type'] = 'module_completed'
        fields[f'module_{activity.pk}_rule_target'] = str(self.first.pk)
        self.assertRedirects(self.post(fields), self.url)
        self.assertFalse(Unit.objects.filter(pk=self.unit.pk).exists())
        self.assertFalse(Module.objects.filter(pk__in=[self.first.pk, self.second.pk, hidden.pk]).exists())
        self.assertFalse(ModuleBranchRule.objects.filter(pk=branch.pk).exists())
        activity.refresh_from_db()
        self.assertFalse(activity.is_locked)
        self.assertEqual(activity.unlock_rule, {})
        for progress_id in preserved_progress_ids:
            progress = ModuleProgress.objects.get(pk=progress_id)
            self.assertTrue(progress.is_complete)
            self.assertEqual(progress.score, 100)
            self.assertTrue(ModuleProgressEvent.objects.filter(module_progress=progress).exists())
        for instance, enrollment in zip((self.instance, other), enrollments):
            instance.refresh_from_db()
            self.assertEqual(instance.grading_policy, {
                'units': {str(keep.pk): {'weight': 1}},
                'groups': [{'unit_ids': [str(keep.pk)], 'deduction': 2}],
            })
            summary = CourseProgress.objects.get(enrollment=enrollment)
            self.assertEqual((summary.total_modules, summary.modules_completed, summary.overall_score), (1, 1, 100))

    def test_move_activities_while_deleting_unit_uses_final_placement(self):
        keep = Unit.objects.create(course=self.course, title='Keep', order=2)
        incoming = Module.objects.create(unit=keep, title='Move into deleted unit')
        fields = self.fields()
        fields.update({f'unit_{self.unit.pk}_delete': '1',
                       f'module_{self.first.pk}_unit_id': str(keep.pk),
                       f'module_{incoming.pk}_unit_id': str(self.unit.pk)})
        self.assertRedirects(self.post(fields), self.url)
        self.first.refresh_from_db()
        self.assertEqual(self.first.unit_id, keep.pk)
        self.assertFalse(Module.objects.filter(pk__in=[incoming.pk, self.second.pk]).exists())

    def test_undo_empty_unit_deletion_and_delete_last_unit(self):
        empty = Unit.objects.create(course=self.course, title='Empty')
        fields = self.fields()
        fields.update({f'unit_{self.unit.pk}_delete': '0', f'unit_{empty.pk}_delete': '1'})
        self.assertRedirects(self.post(fields), self.url)
        self.assertTrue(Unit.objects.filter(pk=self.unit.pk).exists())
        self.assertFalse(Unit.objects.filter(pk=empty.pk).exists())
        fields = self.fields()
        fields[f'unit_{self.unit.pk}_delete'] = '1'
        self.assertRedirects(self.post(fields), self.url)
        self.assertFalse(self.course.units.exists())

    def test_unit_deletion_rolls_back_if_grade_refresh_fails(self):
        fields = self.fields()
        fields[f'unit_{self.unit.pk}_delete'] = '1'
        with patch('modulearn.learning.services.grading.refresh_course_grades', side_effect=ValueError('test rollback')):
            response = self.post(fields)
        self.assertRedirects(response, self.url)
        self.assertTrue(Unit.objects.filter(pk=self.unit.pk).exists())
        self.assertEqual(self.unit.modules.count(), 2)

    def test_unit_deletion_respects_ownership_and_research_lock(self):
        from recruitment.models import RecruitmentSource, ParticipantSession

        fields = self.fields()
        fields[f'unit_{self.unit.pk}_delete'] = '1'
        for is_instructor in (False, True):
            user = User.objects.create_user(username=f'outsider-{is_instructor}', is_instructor=is_instructor)
            self.client.force_login(user)
            self.assertEqual(self.post(fields).status_code, 403)
            self.assertTrue(Unit.objects.filter(pk=self.unit.pk).exists())
        self.client.force_login(self.teacher)
        # Research participants in another session still protect shared units.
        other = CourseInstance.objects.create(course=self.course, group_name='Research')
        source = RecruitmentSource.objects.create(course_instance=other, platform='prolific')
        ParticipantSession.objects.create(recruitment_source=source, external_pid='test')
        self.course.is_locked_for_research = True
        self.course.save(update_fields=['is_locked_for_research'])
        self.assertRedirects(self.post(fields), self.url)
        self.assertTrue(Unit.objects.filter(pk=self.unit.pk).exists())

    def test_foreign_unit_cannot_be_deleted_or_used_as_destination(self):
        other = Course.objects.create(id='unrelated', title='Unrelated')
        foreign = Unit.objects.create(course=other, title='Protected')
        fields = self.fields()
        fields.update({f'unit_{foreign.pk}_delete': '1', f'module_{self.first.pk}_unit_id': str(foreign.pk)})
        self.assertRedirects(self.post(fields), self.url)
        self.assertTrue(Unit.objects.filter(pk=foreign.pk).exists())
        self.first.refresh_from_db()
        self.assertEqual(self.first.unit_id, self.unit.pk)

    def test_delete_unit_clears_explicit_unit_dependencies_on_recommendation_content(self):
        keep = Unit.objects.create(course=self.course, title='Keep')
        activity = Module.objects.create(unit=keep, title='Practice', is_recommendation_only=True,
            is_locked=True, unlock_rule={'conditions': [{'type': 'unit_completed', 'target_id': self.unit.pk}]})
        fields = self.fields()
        fields[f'unit_{self.unit.pk}_delete'] = '1'
        self.assertRedirects(self.post(fields), self.url)
        activity.refresh_from_db()
        self.assertFalse(activity.is_locked)
        self.assertEqual(activity.unlock_rule, {})
