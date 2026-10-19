from django.test import TestCase
from django.urls import reverse
from accounts.models import User
from courses.models import Course, CourseInstance, Unit, Module, Enrollment, ModuleProgress


class AnalyticsDrilldownTests(TestCase):
    def test_saved_metrics_are_scoped_and_exclude_instructor_and_practice(self):
        teacher = User.objects.create_user(username='teacher-drilldown', is_instructor=True)
        student = User.objects.create_user(username='student-drilldown')
        course = Course.objects.create(id='drilldown', title='Drilldown')
        instance = CourseInstance.objects.create(course=course, group_name='A')
        instance.instructors.add(teacher)
        unit = Unit.objects.create(course=course, title='Unit')
        module = Module.objects.create(unit=unit, title='Exercise', platform_name='Examples')
        practice = Module.objects.create(unit=unit, title='Practice', is_recommendation_only=True)
        enrollment = Enrollment.objects.create(student=student, course_instance=instance)
        Enrollment.all_objects.create(student=teacher, course_instance=instance, is_instructor_preview=True)
        progress, _ = ModuleProgress.objects.get_or_create(user=student, enrollment=enrollment, module=module)
        ModuleProgress.objects.filter(pk=progress.pk).update(progress=0, score=0, attempts=2, is_complete=False)
        other = CourseInstance.objects.create(course=course, group_name='B')
        other_enrollment = Enrollment.objects.create(student=student, course_instance=other)
        other_progress, _ = ModuleProgress.objects.get_or_create(user=student, enrollment=other_enrollment, module=module)
        ModuleProgress.objects.filter(pk=other_progress.pk).update(progress=1, score=100, attempts=9, is_complete=True)
        self.client.force_login(teacher)
        url = reverse('dashboard:fetch_modulearn_instance_analytics')
        response = self.client.get(url, {'instance_id': instance.pk})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([learner['id'] for learner in data['learners']], [student.username])
        activities = data['learners'][0]['state']['activities'][str(unit.pk)]
        values = next(group[str(module.pk)]['values'] for group in activities.values() if str(module.pk) in group)
        self.assertEqual(values, {'k': 0, 'p': 0, 'score': 0, 'attempts': 2, 'is_complete': False})
        self.assertFalse(any(str(practice.pk) in group for group in activities.values()))
        ModuleProgress.objects.filter(pk=progress.pk).update(progress=1, score=None, is_complete=True)
        data = self.client.get(url, {'instance_id': instance.pk}).json()
        activities = data['learners'][0]['state']['activities'][str(unit.pk)]
        values = next(group[str(module.pk)]['values'] for group in activities.values() if str(module.pk) in group)
        self.assertIsNone(values['score'])
        self.assertTrue(values['is_complete'])
        self.client.force_login(student)
        self.assertEqual(self.client.get(url, {'instance_id': instance.pk}).status_code, 403)
