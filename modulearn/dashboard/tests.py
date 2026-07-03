from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from courses.models import Course, CourseInstance, Enrollment, Module, ModuleBranchRule, ModuleProgress, ModuleProgressEvent, Unit


@override_settings(
    STORAGES={
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
)
class DashboardViewTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username='student1',
            email='student1@example.com',
            password='safe-pass-123',
            is_student=True,
        )
        self.instructor = User.objects.create_user(
            username='instructor1',
            email='instructor1@example.com',
            password='safe-pass-123',
            is_instructor=True,
            is_student=False,
        )
        self.course = Course.objects.create(id='course-dash', title='Dashboard Course')
        self.course.instructors.add(self.instructor)
        self.instance = CourseInstance.objects.create(course=self.course, group_name='Spring A')
        self.instance.instructors.add(self.instructor)
        Enrollment.objects.create(student=self.student, course_instance=self.instance)

    def test_student_dashboard_renders(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('dashboard:student_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Student Dashboard')
        self.assertContains(response, 'Dashboard Course')

    def test_instructor_dashboard_renders_for_instructor(self):
        self.client.force_login(self.instructor)
        response = self.client.get(reverse('dashboard:instructor_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Instructor Dashboard')
        self.assertContains(response, 'Dashboard Course')

    def test_instructor_recent_activity_names_student(self):
        self.student.full_name = 'Demo Learner'
        self.student.save(update_fields=['full_name'])
        unit = Unit.objects.create(course=self.course, title='Unit 1')
        module = Module.objects.create(unit=unit, title='Variable Assignment')
        enrollment = Enrollment.objects.get(student=self.student, course_instance=self.instance)
        module_progress, _created = ModuleProgress.objects.get_or_create(
            user=self.student,
            enrollment=enrollment,
            module=module,
        )
        ModuleProgressEvent.objects.create(
            module_progress=module_progress,
            user=self.student,
            module=module,
            course_instance=self.instance,
            event_type='completion',
            source='test',
            progress=1.0,
            score=100.0,
            success=True,
        )
        self.client.force_login(self.instructor)

        response = self.client.get(reverse('dashboard:instructor_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Variable Assignment')
        self.assertContains(response, 'Demo Learner')
        self.assertContains(response, 'student1@example.com')
        self.assertContains(response, 'Done')

    def test_instructor_dashboard_redirects_students(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('dashboard:instructor_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard:student_dashboard'))

    def test_instructor_can_create_demo_course(self):
        self.client.force_login(self.instructor)

        response = self.client.post(reverse('dashboard:create_demo_course'))

        instance = CourseInstance.objects.exclude(id=self.instance.id).get()
        self.assertRedirects(response, reverse('courses:course_configuration', kwargs={'instance_id': instance.id}))
        self.assertEqual(instance.course.title, 'Intro to Python - SPLICE Demo Course')
        self.assertTrue(instance.instructors.filter(id=self.instructor.id).exists())
        self.assertTrue(instance.course.instructors.filter(id=self.instructor.id).exists())
        self.assertEqual(Unit.objects.filter(course=instance.course).count(), 10)
        self.assertEqual(Module.objects.filter(unit__course=instance.course).count(), 28)
        self.assertEqual(
            Module.objects.filter(
                unit__course=instance.course,
                module_type=Module.MODULE_TYPE_SPLICE_SMART_CONTENT,
            ).count(),
            28,
        )
        self.assertEqual(Module.objects.filter(unit__course=instance.course, is_locked=True).count(), 27)
        first_module = Module.objects.filter(unit__course=instance.course).order_by('unit__order', 'unit__id', 'order', 'id').first()
        second_module = Module.objects.filter(unit__course=instance.course).order_by('unit__order', 'unit__id', 'order', 'id')[1]
        self.assertFalse(first_module.is_locked)
        self.assertEqual(second_module.unlock_rule_type, 'module_completed')
        self.assertEqual(second_module.unlock_rule_target, first_module.id)

        dashboard_response = self.client.get(reverse('dashboard:instructor_dashboard'))
        self.assertContains(dashboard_response, 'Create Demo Course')
        self.assertNotContains(dashboard_response, 'value="intro_python"')
        self.assertContains(dashboard_response, 'value="adaptive_branching"')

    def test_instructor_can_create_adaptive_branching_demo_course(self):
        self.client.force_login(self.instructor)

        response = self.client.post(reverse('dashboard:create_demo_course'), {
            'demo_type': 'adaptive_branching',
        })

        instance = CourseInstance.objects.exclude(id=self.instance.id).get()
        self.assertRedirects(response, reverse('courses:course_configuration', kwargs={'instance_id': instance.id}))
        self.assertEqual(instance.course.title, 'Adaptive Branching - Demo Course')
        self.assertTrue(instance.instructors.filter(id=self.instructor.id).exists())
        self.assertTrue(instance.course.instructors.filter(id=self.instructor.id).exists())
        self.assertTrue(instance.course.plugin_config['plugins']['adaptive_branching']['enabled'])
        self.assertTrue(instance.course.plugin_config['plugins']['guided_sequence']['enabled'])
        self.assertEqual(Unit.objects.filter(course=instance.course).count(), 1)
        self.assertEqual(Module.objects.filter(unit__course=instance.course).count(), 4)
        self.assertEqual(ModuleBranchRule.objects.filter(course=instance.course).count(), 4)
        self.assertEqual(Module.objects.filter(unit__course=instance.course, is_locked=True).count(), 3)

        dashboard_response = self.client.get(reverse('dashboard:instructor_dashboard'))
        self.assertContains(dashboard_response, 'Create Demo Course')
        self.assertContains(dashboard_response, 'value="intro_python"')
        self.assertNotContains(dashboard_response, 'value="adaptive_branching"')

    def test_demo_course_button_hides_when_all_demos_exist(self):
        self.client.force_login(self.instructor)

        self.client.post(reverse('dashboard:create_demo_course'), {
            'demo_type': 'intro_python',
        })
        self.client.post(reverse('dashboard:create_demo_course'), {
            'demo_type': 'adaptive_branching',
        })

        dashboard_response = self.client.get(reverse('dashboard:instructor_dashboard'))
        self.assertNotContains(dashboard_response, 'Create Demo Course')

    def test_students_cannot_create_demo_course(self):
        self.client.force_login(self.student)

        response = self.client.post(reverse('dashboard:create_demo_course'))

        self.assertRedirects(response, reverse('dashboard:student_dashboard'))
        self.assertFalse(Course.objects.filter(title='Intro to Python - SPLICE Demo Course').exists())
