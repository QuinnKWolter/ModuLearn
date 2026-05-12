from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from courses.models import Course, CourseInstance, Enrollment


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
        self.assertContains(response, 'Instructor Workspace')
        self.assertContains(response, 'Dashboard Course')

    def test_instructor_dashboard_redirects_students(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('dashboard:instructor_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard:student_dashboard'))
