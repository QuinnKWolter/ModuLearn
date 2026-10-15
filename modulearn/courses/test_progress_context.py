import json
from urllib.parse import urlencode
from django.test import TestCase, RequestFactory
from django.http import HttpResponse
from django.urls import reverse
from accounts.models import User
from courses.models import Course, CourseInstance, Enrollment, Unit, Module, ModuleProgress
from modulearn.learning.services.pcrs_tracking import capture_pcrs_result_if_possible
from modulearn.learning.services.tracking_context import enrolled_tracking_session
from modulearn.views_proxy import _pcex_local_progress_context


class ProgressContextTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='context-student')
        self.course=Course.objects.create(id='context',title='Course')
        self.first=CourseInstance.objects.create(course=self.course,group_name='Same name')
        self.second=CourseInstance.objects.create(course=self.course,group_name='Other session')
        unit=Unit.objects.create(course=self.course,title='Unit')
        self.module=Module.objects.create(unit=unit,title='Problem',content_url='https://pcrs.utm.utoronto.ca/mgrids/problems/java/1/embed')
        self.enrollment=Enrollment.objects.create(student=self.user,course_instance=self.first)
        self.other=Enrollment.objects.create(student=self.user,course_instance=self.second)
        self.params={'cid':self.course.pk,'usr':self.user.username,'grp':'Same name',
                     'course_instance_id':str(self.first.pk),'module_id':str(self.module.pk)}

    def test_exact_session_survives_rename(self):
        self.assertEqual(enrolled_tracking_session(self.course,self.user,self.params),self.first)
        self.first.group_name='Renamed';self.first.save()
        self.assertEqual(_pcex_local_progress_context(self.params)[2],self.first)
        self.params['course_instance_id']='999999'
        self.assertIsNone(enrolled_tracking_session(self.course,self.user,self.params))

    def test_ambiguous_legacy_callback_does_not_guess(self):
        self.params.pop('course_instance_id')
        self.params.pop('grp')
        self.assertIsNone(enrolled_tracking_session(self.course,self.user,self.params))
        self.other.active=False;self.other.save()
        self.assertEqual(enrolled_tracking_session(self.course,self.user,self.params),self.first)

    def test_pcrs_updates_requested_session_and_recreates_missing_progress(self):
        ModuleProgress.objects.filter(enrollment=self.enrollment).delete()
        request=RequestFactory().post('/run',{'submission':'code'},HTTP_REFERER='http://testserver/embed?'+urlencode(self.params))
        request.user=self.user
        capture_pcrs_result_if_possible(request,'pcrs.utm.utoronto.ca','mgrids/problems/java/1/run',
            HttpResponse(json.dumps({'score':1,'max_score':1}),content_type='application/json'))
        progress=ModuleProgress.objects.get(enrollment=self.enrollment,module=self.module)
        self.assertTrue(progress.is_complete);self.assertEqual(progress.attempts,1)
        self.assertTrue(progress.events.filter(source='pcrs').exists())
        self.assertEqual(ModuleProgress.objects.get(enrollment=self.other,module=self.module).attempts,0)

    def test_course_author_role_does_not_drop_attempt_in_student_session(self):
        self.course.instructors.add(self.user)
        self.client.force_login(self.user)
        response=self.client.post(reverse('courses:update_module_progress',args=[self.module.pk]),
            {'course_instance_id':self.first.pk,'data':[{'completion':True,'score':100,'progress':100,'success':True}]},content_type='application/json')
        self.assertEqual(response.status_code,200)
        self.assertTrue(ModuleProgress.objects.get(enrollment=self.enrollment,module=self.module).is_complete)
        self.assertFalse(ModuleProgress.objects.get(enrollment=self.other,module=self.module).is_complete)

    def test_instructor_preview_cannot_reuse_another_sessions_student_record(self):
        self.second.instructors.add(self.user)
        preview,_=ModuleProgress.get_or_create_progress(self.user,self.module,self.second)
        self.assertIsNone(preview.enrollment_id)
        self.assertFalse(ModuleProgress.objects.get(enrollment=self.enrollment,module=self.module).is_complete)

    def test_instructor_without_enrollment_can_send_preview_events(self):
        teacher = User.objects.create_user(username='preview-teacher', is_instructor=True)
        self.first.instructors.add(teacher)
        self.client.force_login(teacher)
        before = list(ModuleProgress.objects.order_by('pk').values())
        endpoint = reverse('courses:update_module_progress', args=[self.module.pk])
        response = self.client.post(endpoint, {'course_instance_id': self.first.pk,
            'provider_event': {'message': {'type': 'cupcake:log'}}}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['message'], 'Progress not tracked for instructors')
        self.assertEqual(before, list(ModuleProgress.objects.order_by('pk').values()))
        self.assertFalse(Enrollment.objects.filter(student=teacher).exists())
        response = self.client.post(endpoint, {'course_instance_id': self.second.pk}, content_type='application/json')
        self.assertEqual(response.status_code, 404)

    def test_animation_interactions_are_logged_once_without_awarding_credit(self):
        from modulearn.learning.services.splice_tracking import record_splice_event
        progress=ModuleProgress.objects.get(enrollment=self.enrollment,module=self.module)
        event={'event_id':'animation-steps-1','message':{'subject':'SPLICE.sendEvent','data':{'log':[[1,'step',1],[2,'step',2]]}}}
        record_splice_event(progress,event);record_splice_event(progress,event)
        progress.refresh_from_db()
        self.assertEqual(progress.events.filter(event_type='provider_event',source='splice').count(),1)
        self.assertEqual(progress.attempts,0);self.assertFalse(progress.is_complete)
        self.assertEqual(progress.events.get().payload['splice'],event['message'])
