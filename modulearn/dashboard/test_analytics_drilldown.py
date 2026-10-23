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

class GradingAnalyticsTests(TestCase):
    def setUp(self):
        self.teacher=User.objects.create_user(username='analytics-teacher',is_instructor=True)
        self.student=User.objects.create_user(username='analytics-student')
        self.course=Course.objects.create(id='analytics-grades',title='Grades')
        self.instance=CourseInstance.objects.create(course=self.course,grading_policy={'mode':'units','target':50})
        self.instance.instructors.add(self.teacher)
        self.unit=Unit.objects.create(course=self.course,title='Unit')
        self.modules=[Module.objects.create(unit=self.unit,title=str(i),is_graded=i<2) for i in range(3)]
        self.enrollment=Enrollment.objects.create(student=self.student,course_instance=self.instance)
        self.client.force_login(self.teacher)

    def test_effective_grade_unit_target_last_activity_and_practice(self):
        from django.utils import timezone
        from modulearn.learning.services.progress import recompute_course_progress
        ModuleProgress.objects.filter(enrollment=self.enrollment,module=self.modules[0]).update(is_complete=True,progress=.4,score=25,attempts=1,completed_at=timezone.now())
        ModuleProgress.objects.filter(enrollment=self.enrollment,module=self.modules[2]).update(is_complete=True,progress=1,score=100)
        url=reverse('dashboard:fetch_modulearn_instance_analytics')
        learner=self.client.get(url,{'instance_id':self.instance.id}).json()['learners'][0]
        self.assertEqual(learner['grading'],{'progress':50,'units_met':1,'units_total':1})
        self.assertIsNotNone(learner['lastActive'])
        self.assertEqual(learner['state']['topics'][str(self.unit.id)]['overall']['p'],.5)
        Module.objects.filter(unit=self.unit).update(is_graded=False)
        grade=recompute_course_progress(self.enrollment)
        self.assertEqual(grade.total_modules,3)
        self.assertEqual(grade.modules_completed,2)
        self.assertEqual(grade.practice_total,0)
        learner=self.client.get(url,{'instance_id':self.instance.id}).json()['learners'][0]
        self.assertAlmostEqual(learner['grading']['progress'],200/3)

    def test_lazy_events_and_permissions(self):
        from courses.models import ModuleProgressEvent
        progress=ModuleProgress.objects.get(enrollment=self.enrollment,module=self.modules[0])
        ModuleProgressEvent.objects.create(module_progress=progress,module=progress.module,user=self.student,course_instance=self.instance,event_type='progress',progress=.5,payload={'answer':'private response'})
        url=reverse('dashboard:fetch_modulearn_student_engagement')
        params={'instance_id':self.instance.id,'learner_id':self.student.username,'summary':'1'}
        response=self.client.get(url,params)
        self.assertEqual(response.status_code,200)
        module=response.json()['units'][0]['modules'][0]
        self.assertEqual(module['events'],[])
        self.assertEqual(module['event_count'],1)
        self.assertEqual(module['timeline'][0]['progress'],.5)
        self.assertNotIn('private response',response.content.decode())
        details=self.client.get(url,dict(params,module_id=self.modules[0].id)).json()
        self.assertEqual(len(details['events']),1)
        self.assertEqual(self.client.get(url,dict(params,module_id=99999)).status_code,404)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(url,dict(params,module_id=self.modules[0].id)).status_code,403)

    def test_last_active_launch_and_student_course_stars(self):
        from courses.models import ModuleAccessLog
        from modulearn.learning.selectors.courses import build_course_detail_context
        url=reverse('dashboard:fetch_modulearn_instance_analytics')
        params={'instance_id':self.instance.id}
        self.assertIsNone(self.client.get(url,params).json()['learners'][0]['lastActive'])
        log=ModuleAccessLog.objects.create(enrollment=self.enrollment,user=self.student,
            module=self.modules[0],course_instance=self.instance,event_type='launch')
        self.assertIsNotNone(self.client.get(url,params).json()['learners'][0]['lastActive'])
        context=build_course_detail_context(self.student,self.instance)
        cards=context['unit_cards']
        self.assertEqual(cards[0]['module_count'],2)
        self.assertEqual(sum(m['is_graded'] for m in cards[0]['modules']),2)
        Module.objects.filter(unit=self.unit).update(is_graded=False)
        context=build_course_detail_context(self.student,self.instance)
        self.assertEqual(context['unit_cards'][0]['module_count'],3)
        self.assertTrue(all(m['is_graded'] for m in context['unit_cards'][0]['modules']))
