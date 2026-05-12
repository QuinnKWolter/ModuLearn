from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from courses.models import (
    Course,
    CourseInstance,
    CourseProgress,
    Enrollment,
    EnrollmentCode,
    Module,
    ModuleAccessLog,
    ModuleForm,
    ModuleFormAnswer,
    ModuleFormQuestion,
    ModuleFormSubmission,
    ModuleProgress,
    ModuleProgressEvent,
    Unit,
)
from modulearn.learning.services.progress import apply_progress_snapshot
from modulearn.learning.selectors.courses import build_course_detail_context


class CourseProgressTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='student-course',
            email='student-course@example.com',
            password='safe-pass-123',
            is_student=True,
        )
        self.instructor = User.objects.create_user(
            username='instructor-course',
            email='instructor-course@example.com',
            password='safe-pass-123',
            is_instructor=True,
            is_student=False,
        )
        self.course = Course.objects.create(id='course-1', title='Biology 101')
        self.course.instructors.add(self.instructor)
        self.instance = CourseInstance.objects.create(course=self.course, group_name='Fall 2026')
        self.instance.instructors.add(self.instructor)
        self.unit = Unit.objects.create(course=self.course, title='Unit 1')
        self.module_a = Module.objects.create(unit=self.unit, title='Module A')
        self.module_b = Module.objects.create(unit=self.unit, title='Module B')
        self.enrollment = Enrollment.objects.create(student=self.student, course_instance=self.instance)

    def test_enrollment_signal_creates_progress_rows_once(self):
        self.assertEqual(CourseProgress.objects.filter(enrollment=self.enrollment).count(), 1)
        self.assertEqual(ModuleProgress.objects.filter(enrollment=self.enrollment).count(), 2)

    def test_progress_completion_sets_completed_at_and_event(self):
        module_progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.module_a)
        apply_progress_snapshot(
          module_progress,
          source='test',
          progress=1.0,
          score=95.0,
          success=True,
        )

        module_progress.refresh_from_db()
        self.assertTrue(module_progress.is_complete)
        self.assertIsNotNone(module_progress.completed_at)
        self.assertTrue(
            ModuleProgressEvent.objects.filter(module_progress=module_progress, event_type='completion').exists()
        )

    def test_course_progress_rollup_sets_completed_at_when_all_modules_complete(self):
        for module_progress in ModuleProgress.objects.filter(enrollment=self.enrollment):
            apply_progress_snapshot(
                module_progress,
                source='test',
                progress=1.0,
                score=100.0,
                success=True,
            )

        course_progress = CourseProgress.objects.get(enrollment=self.enrollment)
        self.assertEqual(course_progress.modules_completed, 2)
        self.assertEqual(course_progress.total_modules, 2)
        self.assertEqual(course_progress.overall_progress, 100.0)
        self.assertIsNotNone(course_progress.completed_at)

    def test_invite_code_enrollment_creates_one_enrollment_and_progress_set(self):
        Enrollment.objects.filter(student=self.student, course_instance=self.instance).delete()
        CourseProgress.objects.all().delete()
        ModuleProgress.objects.all().delete()

        invitation = EnrollmentCode.objects.create(
            code='INVITE123',
            email='invited@example.com',
            course_instance=self.instance,
        )

        response = self.client.post(reverse('courses:enroll_with_code'), {
            'email': 'invited@example.com',
            'code': 'INVITE123',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Enrollment.objects.filter(course_instance=self.instance, student__email='invited@example.com').count(), 1)

        enrollment = Enrollment.objects.get(course_instance=self.instance, student__email='invited@example.com')
        self.assertEqual(CourseProgress.objects.filter(enrollment=enrollment).count(), 1)
        self.assertEqual(ModuleProgress.objects.filter(enrollment=enrollment).count(), 2)

        invitation.refresh_from_db()
        self.assertTrue(invitation.used)

    def test_hidden_modules_are_not_in_student_course_context(self):
        self.module_b.is_visible = False
        self.module_b.save(update_fields=['is_visible'])

        context = build_course_detail_context(self.student, self.instance)
        visible_titles = [
            item['title']
            for card in context['unit_cards']
            for item in card['modules']
        ]

        self.assertIn('Module A', visible_titles)
        self.assertNotIn('Module B', visible_titles)

    def test_locked_module_blocks_student_launch_and_logs_denial(self):
        self.client.force_login(self.student)
        self.module_a.is_locked = True
        self.module_a.unlock_rule = {'mode': 'all', 'conditions': [{'type': 'module_completed', 'target_id': self.module_b.id}]}
        self.module_a.save(update_fields=['is_locked', 'unlock_rule'])

        response = self.client.get(reverse('courses:launch_iframe_module', args=[self.instance.id, self.module_a.id]))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ModuleAccessLog.objects.filter(
                user=self.student,
                module=self.module_a,
                course_instance=self.instance,
                event_type=ModuleAccessLog.EVENT_UNLOCK_DENIED,
            ).exists()
        )

    def test_form_module_submission_marks_module_complete_and_logs_access(self):
        form_module = Module.objects.create(
            unit=self.unit,
            title='Reflection',
            module_type=Module.MODULE_TYPE_FORM,
            order=30,
        )
        module_form = ModuleForm.objects.create(module=form_module)
        question = ModuleFormQuestion.objects.create(
            form=module_form,
            prompt='How confident are you?',
            question_type=ModuleFormQuestion.TYPE_SHORT_ANSWER,
            required=True,
            order=10,
        )
        ModuleProgress.get_or_create_progress(self.student, form_module, self.instance)
        self.client.force_login(self.student)

        response = self.client.post(
            reverse('courses:launch_iframe_module', args=[self.instance.id, form_module.id]),
            {f'question_{question.id}': 'Very confident'},
        )

        self.assertEqual(response.status_code, 302)
        progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=form_module)
        self.assertTrue(progress.is_complete)
        self.assertEqual(progress.progress, 1.0)
        self.assertTrue(ModuleFormSubmission.objects.filter(form=module_form, user=self.student).exists())
        self.assertTrue(ModuleFormAnswer.objects.filter(question=question, text_value='Very confident').exists())
        self.assertTrue(
            ModuleAccessLog.objects.filter(
                user=self.student,
                module=form_module,
                event_type=ModuleAccessLog.EVENT_FORM_SUBMIT,
            ).exists()
        )
