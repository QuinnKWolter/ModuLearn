import json
from django.test import TestCase
from django.urls import reverse
from accounts.models import User
from courses.models import Course, CourseInstance, Unit, Module, Enrollment, ModuleProgress


class ActivityInterfaceTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='activity-teacher', is_instructor=True)
        self.student = User.objects.create_user(username='activity-student')
        self.course = Course.objects.create(id='activity-ui', title='Activities')
        self.instance = CourseInstance.objects.create(course=self.course)
        self.instance.instructors.add(self.teacher)
        self.unit = Unit.objects.create(course=self.course, title='Unit')
        self.module = Module.objects.create(unit=self.unit, title='Exercise')
        self.enrollment = Enrollment.objects.create(student=self.student, course_instance=self.instance)

    def test_builder_preserves_question_types_and_order(self):
        self.client.force_login(self.teacher)
        questions = [
            {'prompt': 'Explain', 'question_type': 'long_answer', 'required': False},
            {'prompt': 'Choose one', 'question_type': 'single_choice', 'options': ['Python', 'Java']},
            {'prompt': 'Choose several', 'question_type': 'multiple_choice', 'options': ['A', 'B']},
            {'prompt': 'Confidence', 'question_type': 'likert', 'likert_min_label': 'Low', 'likert_max_label': 'High'},
            {'prompt': 'Short response', 'question_type': 'short_answer'},
        ]
        response = self.client.post(reverse('courses:course_configuration', args=[self.instance.id]), {
            'action': 'add_module', 'unit_id': self.unit.id, 'module_type': 'form',
            'title': 'Builder test', 'questions_json': json.dumps(questions),
        })
        self.assertEqual(response.status_code, 302)
        activity = Module.objects.get(unit=self.unit, title='Builder test')
        saved = list(activity.form.questions.order_by('order'))
        self.assertEqual([q.prompt for q in saved], [q['prompt'] for q in questions])
        self.assertFalse(saved[0].required)
        self.assertEqual(saved[1].options, ['Python', 'Java'])
        self.assertEqual(saved[3].likert_min_label, 'Low')

    def test_completion_styles_and_configuration_stars(self):
        ModuleProgress.objects.filter(enrollment=self.enrollment, module=self.module).update(is_complete=True, progress=1)
        self.client.force_login(self.student)
        response = self.client.get(reverse('courses:course_detail', args=[self.instance.id]))
        self.assertContains(response, 'Completed activity')
        self.assertContains(response, 'completed-activity-title')
        self.assertContains(response, 'is-earned')
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('courses:course_configuration', args=[self.instance.id]))
        self.assertContains(response, 'Add Activity')
        self.assertNotContains(response, 'Add Module')
        self.assertContains(response, f'data-grade-star="{self.module.id}"', count=2)
