import json
from urllib.parse import urlencode
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.core.exceptions import PermissionDenied

from accounts.models import User
from courses.models import (Course, CourseInstance, Unit, Module, Enrollment, ModuleProgress, CourseProgress,
    StaticRecommendationSet, RecommendationProgress, RecommendationActivation, RecommendationEvent)
from courses.test_static_recommendations import parse_uploads, rec_file
from modulearn.learning.services.progress import apply_progress_snapshot
from modulearn.learning.services.recommendation_tracking import practice_items, proxy_progress


@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class PracticeTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='teacher', is_instructor=True)
        self.student = User.objects.create_user(username='student', is_student=True)
        self.course = Course.objects.create(id='practice', title='Practice', plugin_config={'plugins': {'static_recommendations': {'enabled': True}}})
        self.course.instructors.add(self.teacher)
        self.instance = CourseInstance.objects.create(course=self.course, group_name='practice')
        self.instance.instructors.add(self.teacher)
        self.unit = Unit.objects.create(course=self.course, title='Basics')
        self.source = Module.objects.create(unit=self.unit, title='Challenge', provider_id='pcex_ch', content_url='https://acos.cs.vt.edu/html/acos-pcex/acos-pcex-examples/demo')
        self.target = Module.objects.create(unit=self.unit, title='Example', provider_id='pcex', content_url='https://acos.cs.vt.edu/html/acos-pcex/acos-pcex-examples/example')
        self.enrollment = Enrollment.objects.create(student=self.student, course_instance=self.instance)
        self.dataset = StaticRecommendationSet.objects.create(course=self.course,course_instance=self.instance, **parse_uploads([rec_file()]))
        self.progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.source)
        self.client.force_login(self.student)

    def attempt(self, score=0, number=None):
        payload = {'pcrs_result': {'score': score, 'max_score': 100}}
        apply_progress_snapshot(self.progress, source='pcrs', score=max(score, self.progress.score or 0),
            progress=score/100, success=score==100, payload=payload, event_type='progress')

    def activate(self):
        self.attempt(); self.attempt()
        return RecommendationProgress.objects.get(activation__enrollment=self.enrollment)

    def test_splice_interaction_logs_stay_in_practice_and_are_retry_safe(self):
        item=self.activate()
        before=list(ModuleProgress.objects.values('id','score','attempts','progress','is_complete'))
        url=reverse('courses:recommendation_practice_progress',args=[self.instance.pk,item.pk])
        payload={'splice_event':{'event_id':'steps-1','message':{'subject':'SPLICE.sendEvent','data':{'log':[[1,'step',1]]}}}}
        for _ in range(2):
            self.assertEqual(self.client.post(url,payload,content_type='application/json').status_code,200)
        self.assertEqual(item.events.filter(source='splice',event_type='provider_event').count(),1)
        self.assertEqual(before,list(ModuleProgress.objects.values('id','score','attempts','progress','is_complete')))

    def test_instructor_recommendations_save_separate_scores_and_student_still_needs_failure(self):
        self.client.force_login(self.teacher)
        before = list(ModuleProgress.objects.order_by('pk').values())
        url = reverse('courses:recommendation_queue', args=[self.instance.pk])
        response = self.client.get(url, {'source': self.source.pk})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['instructor_testing'])
        item = response.json()['items'][0]
        self.assertEqual(item['module_id'], self.target.pk)
        practice = RecommendationProgress.objects.get(pk=item['id'])
        self.assertTrue(practice.enrollment.is_instructor_preview)
        self.assertIn('event_url', item)
        self.assertEqual(practice.activation.failures, 0)
        self.assertFalse(RecommendationEvent.objects.exists())
        apply_progress_snapshot(practice, source='splice', score=100, progress=1, is_complete=True)
        self.assertEqual(self.client.get(url, {'source': self.source.pk}).json()['items'][0]['score'], 100)
        self.assertEqual(before, list(ModuleProgress.objects.filter(user=self.student).order_by('pk').values()))
        self.assertFalse(Enrollment.objects.filter(student=self.teacher).exists())
        # Instructor practice must never appear in student research exports.
        for download in ('course_csv', 'csv', 'summary'):
            exported = self.client.get(reverse('courses:recommendation_logs', args=[self.instance.pk]), {'download': download})
            content = b''.join(exported.streaming_content) if exported.streaming else exported.content
            self.assertNotIn(b'teacher,', content)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(url, {'source': self.source.pk}).json()['items'], [])
        outsider = User.objects.create_user(username='preview-outsider', is_instructor=True)
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(url, {'source': self.source.pk}).status_code, 403)
        self.client.force_login(self.teacher)
        self.dataset.enabled = False
        self.dataset.save()
        self.assertEqual(self.client.get(url, {'source': self.source.pk}).json()['items'], [])

    def test_quizjet_session_instructor_can_preview_without_student_enrollment(self):
        from modulearn.learning.services.quizjet_tracking import process_quizjet_response
        before = list(ModuleProgress.objects.order_by('pk').values())
        for method in ['get', 'post']:
            request = getattr(RequestFactory(), method)('/proxy/quizjet/', {
                'module_id': self.source.pk, 'course_instance_id': self.instance.pk, 'inputans': '42'})
            request.user = self.teacher
            response = process_quizjet_response(request, 'pawscomp2.sis.pitt.edu', 'quizjet/EvaluateAnswer',
                HttpResponse('<form><b>CORRECT!</b></form>', content_type='text/html'))
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'name="course_instance_id"', response.content)
        self.assertEqual(before, list(ModuleProgress.objects.filter(user=self.student).order_by('pk').values()))
        self.assertFalse(Enrollment.objects.filter(student=self.teacher).exists())
        self.assertTrue(ModuleProgress.objects.get(user=self.teacher, module=self.source).is_complete)
        from modulearn.learning.selectors.timelines import get_course_instance_recent_activity
        self.assertEqual(get_course_instance_recent_activity(self.instance), [])

    def test_quizjet_preview_rejects_outsider_and_invalid_practice_token(self):
        from modulearn.learning.services.quizjet_tracking import process_quizjet_response
        outsider = User.objects.create_user(username='quizjet-outsider', is_instructor=True)
        for user, extra in [(outsider, {}), (self.teacher, {'recommendation': 'invalid'}),
                            (self.teacher, {'module_id': 'invalid'})]:
            request = RequestFactory().get('/proxy/quizjet/', {
                'module_id': self.source.pk, 'course_instance_id': self.instance.pk, **extra})
            request.user = user
            response = process_quizjet_response(request, 'pawscomp2.sis.pitt.edu', 'quizjet/displayQuiz.jsp',
                HttpResponse('<form></form>', content_type='text/html'))
            self.assertEqual(response.status_code, 403)

    def pcrs_practice_callback(self, item, score, **context):
        from modulearn.learning.services.pcrs_tracking import capture_pcrs_result_if_possible
        path = 'mgrids/problems/python/337/run'
        params = {'cid': self.course.pk, 'usr': self.student.username,
                  'course_instance_id': self.instance.pk, 'module_id': self.target.pk,
                  'recommendation': str(item.pk), **context}
        request = RequestFactory().post('/proxy/https/pcrs.utm.utoronto.ca/' + path,
            data=urlencode({'submission': 'print(42)'}),
            content_type='application/x-www-form-urlencoded')
        request.user = self.student
        request.META['HTTP_REFERER'] = (
            'http://testserver/proxy/https/pcrs.utm.utoronto.ca/mgrids/problems/python/337/embed?'
            + urlencode(params))
        response = HttpResponse(json.dumps({'score': score, 'max_score': 5,
            'results': [{'passed': score == 5}]}), content_type='application/json')
        capture_pcrs_result_if_possible(request, 'pcrs.utm.utoronto.ca', path, response)

    def test_pcrs_callback_records_practice_attempts_without_course_credit(self):
        from courses.models import ModuleProgressEvent
        item = self.activate()
        self.target.provider_id = 'pcrs'
        self.target.content_url = 'https://pcrs.utm.utoronto.ca/mgrids/problems/python/337/embed'
        self.target.save()
        normal_before = list(ModuleProgress.objects.order_by('pk').values())
        course_before = list(CourseProgress.objects.order_by('pk').values())
        events_before = ModuleProgressEvent.objects.count()
        with patch.object(CourseProgress, 'submit_grade_to_canvas') as submit:
            self.pcrs_practice_callback(item, 2)
            item.refresh_from_db()
            self.assertEqual((item.score, item.progress, item.attempts, item.is_complete),
                             (40, .4, 1, False))
            self.pcrs_practice_callback(item, 5)
            item.refresh_from_db()
            self.assertEqual((item.score, item.progress, item.attempts, item.is_complete),
                             (100, 1, 2, True))
            submit.assert_not_called()
        attempts = list(item.events.filter(source='pcrs', event_type='attempt').order_by('pk'))
        self.assertEqual([event.score for event in attempts], [40, 100])
        self.assertEqual([event.success for event in attempts], [False, True])
        self.assertEqual(item.events.filter(event_type='completion').count(), 1)
        for event in attempts:
            self.assertEqual(event.payload['pcrs_submission']['form']['submission'], 'print(42)')
            self.assertIn('results', event.payload['pcrs_result'])
        self.assertEqual(normal_before, list(ModuleProgress.objects.order_by('pk').values()))
        self.assertEqual(course_before, list(CourseProgress.objects.order_by('pk').values()))
        self.assertEqual(events_before, ModuleProgressEvent.objects.count())

    def test_pcrs_callback_invalid_practice_context_never_falls_back_to_coursework(self):
        item = self.activate()
        before = list(ModuleProgress.objects.order_by('pk').values())
        event_count = RecommendationEvent.objects.count()
        for context in ({'recommendation': 'invalid'}, {'module_id': self.source.pk}):
            with self.subTest(context=context), self.assertLogs(
                    'modulearn.learning.services.pcrs_tracking', level='ERROR'):
                self.pcrs_practice_callback(item, 5, **context)
        item.refresh_from_db()
        self.assertEqual(item.attempts, 0)
        self.assertFalse(item.is_complete)
        self.assertEqual(before, list(ModuleProgress.objects.order_by('pk').values()))
        self.assertEqual(event_count, RecommendationEvent.objects.count())

    def test_two_failures_activate_and_success_never_removes_assignments(self):
        self.dataset.options = {'failure_threshold': 2}; self.dataset.save()
        self.attempt(); self.assertEqual(practice_items(self.enrollment), [])
        self.attempt(); items=practice_items(self.enrollment);self.assertEqual(len(items),1)
        self.attempt(100);self.assertEqual(practice_items(self.enrollment)[0]['id'],items[0]['id'])
        self.assertEqual(list(RecommendationEvent.objects.filter(event_type='source_attempt').order_by('id').values_list('score',flat=True)),[0,0,100])

    def test_default_requires_one_incorrect_attempt_and_is_problem_specific(self):
        self.assertEqual(practice_items(self.enrollment, self.source.pk), [])
        self.attempt(100)
        self.assertEqual(practice_items(self.enrollment, self.source.pk), [])
        self.attempt(0)
        self.assertEqual(len(practice_items(self.enrollment, self.source.pk)), 1)
        self.assertEqual(practice_items(self.enrollment, self.target.pk), [])

    def test_custom_threshold_and_non_attempt_events(self):
        self.dataset.options={'failure_threshold':3};self.dataset.save()
        apply_progress_snapshot(self.progress,source='pcex_worked_example',score=0,progress=.1)
        self.assertFalse(RecommendationActivation.objects.exists())
        self.attempt();self.attempt();self.assertEqual(practice_items(self.enrollment),[])
        self.attempt();self.assertEqual(len(practice_items(self.enrollment)),1)

    def test_practice_completion_cannot_change_course_progress_or_grade(self):
        item=self.activate()
        normal=ModuleProgress.objects.get(enrollment=self.enrollment,module=self.target)
        before=CourseProgress.objects.get(enrollment=self.enrollment)
        baseline=(before.overall_progress,before.overall_score,before.modules_completed)
        with patch.object(CourseProgress,'submit_grade_to_canvas') as submit:
            apply_progress_snapshot(item,source='splice',progress=1,score=100,is_complete=True,success=True,payload={'answer':'yes'})
            submit.assert_not_called()
        normal.refresh_from_db();self.assertFalse(normal.is_complete);self.assertEqual(normal.attempts,0)
        before.refresh_from_db();self.assertEqual((before.overall_progress,before.overall_score,before.modules_completed),baseline)
        self.assertTrue(practice_items(self.enrollment)[0]['is_complete'])

    def test_normal_completion_does_not_complete_practice(self):
        item=self.activate()
        normal=ModuleProgress.objects.get(enrollment=self.enrollment,module=self.target)
        apply_progress_snapshot(normal,source='test',progress=1,score=100,is_complete=True)
        item.refresh_from_db();self.assertFalse(item.is_complete)

    def test_same_recommendation_under_two_problems_is_separate(self):
        first=self.activate()
        second=Module.objects.create(unit=self.unit,title='Second',provider_id='pcrs')
        activation=RecommendationActivation.objects.create(enrollment=self.enrollment,source_module=second)
        other=RecommendationProgress.objects.create(activation=activation,module=self.target,provider='pcex',rank=1,similarity=.8)
        apply_progress_snapshot(first,source='splice',progress=1,score=100,is_complete=True)
        other.refresh_from_db();self.assertFalse(other.is_complete)

    def test_launch_does_not_record_normal_course_activity(self):
        item=self.activate()
        response=self.client.get(reverse('courses:recommendation_practice',args=[self.instance.pk,item.pk]))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'recommendation='+str(item.pk))
        self.assertContains(response,'/practice/'+str(item.pk)+'/progress/')
        self.assertNotContains(response,'data-queue=')
        self.assertFalse(self.target.progress_events.exists())

    def test_unauthorized_and_wrong_module_contexts_fail_closed(self):
        item=self.activate()
        outsider=User.objects.create_user(username='outsider')
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse('courses:recommendation_practice',args=[self.instance.pk,item.pk])).status_code,403)
        from django.test import RequestFactory
        request=RequestFactory().get('/');request.user=self.student
        with self.assertRaises(PermissionDenied):
            proxy_progress(request,{'recommendation':[str(item.pk)]},user=self.student,module=self.source,course_instance=self.instance)
        with self.assertRaises(PermissionDenied):
            proxy_progress(request,{'recommendation':['invalid']},user=self.student,module=self.target,course_instance=self.instance)

    def test_feedback_requires_completion_and_records_skip_and_rating(self):
        item=self.activate();url=reverse('courses:recommendation_event',args=[self.instance.pk,item.pk])
        self.assertEqual(self.client.post(url,json.dumps({'event_type':'feedback','value':'up'}),content_type='application/json').status_code,400)
        apply_progress_snapshot(item,source='splice',progress=1,score=100,is_complete=True)
        for value in ['skipped','up','down']:
            self.assertEqual(self.client.post(url,json.dumps({'event_type':'feedback','value':value}),content_type='application/json').status_code,200)
        self.assertEqual(item.events.filter(event_type='feedback').count(),3)
        item.refresh_from_db();self.assertEqual(item.feedback,'down')

    def test_disabled_plugin_and_other_enrollment(self):
        item=self.activate()
        other=Enrollment.objects.create(student=self.student,course_instance=CourseInstance.objects.create(course=self.course,group_name='other'))
        self.assertEqual(practice_items(other),[])
        self.dataset.enabled=False;self.dataset.save()
        self.assertEqual(self.client.get(reverse('courses:recommendation_practice',args=[self.instance.pk,item.pk])).status_code,403)

    def test_instructor_logs_permissions_filter_and_csv(self):
        item=self.activate();url=reverse('courses:recommendation_logs',args=[self.instance.pk])
        self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(url),'source_attempt')
        response=self.client.get(url,{'download':'csv','event':'source_attempt'})
        text=b''.join(response.streaming_content).decode()
        self.assertIn('attempt_score',text);self.assertEqual(text.count('source_attempt'),2)

    def test_duplicate_pcex_submission_is_not_two_failures(self):
        payload={'pcex_result':{'attempt_count':1,'result_type':'incorrect','result':False}}
        for _ in range(2):
            apply_progress_snapshot(self.progress,source='pcex',score=0,success=False,payload=payload)
        self.assertEqual(RecommendationActivation.objects.get().failures,1)

    def populate_recommendation_types(self):
        source_key=self.dataset.edges[0]['source']
        self.dataset.edges=[]
        for n,provider in enumerate(['animatedexamples','pcex','quizjet']):
            for rank in range(1,4):
                key=f'{provider}-{rank}'
                Module.objects.create(unit=self.unit,title=key,provider_id=provider)
                self.dataset.nodes[key]={'title':key,'provider':provider,'topic':''}
                self.dataset.edges.append({'source':source_key,'target':key,'provider':provider,'rank':rank,'similarity':.9-n*.1-rank*.01})
        self.dataset.save()

    def test_default_top_two_per_type_and_frozen_assignment(self):
        self.populate_recommendation_types()
        self.attempt();self.attempt()
        items=RecommendationProgress.objects.all()
        self.assertEqual(items.count(),6)
        for provider in ['animatedexamples','pcex','quizjet']:
            self.assertEqual(list(items.filter(provider=provider).order_by('rank').values_list('rank',flat=True)),[1,2])
        self.dataset.edges=[];self.dataset.save()
        self.assertEqual(len(practice_items(self.enrollment)),6)
        with patch('modulearn.learning.services.recommendation_tracking.resolve_nodes') as resolve:
            self.attempt(100)
            resolve.assert_not_called()
        self.assertEqual(RecommendationEvent.objects.filter(event_type='source_attempt').count(),3)

    def test_custom_limit_and_sparse_type_do_not_fill_from_other_types(self):
        self.populate_recommendation_types()
        self.dataset.options={'limit':3}
        self.dataset.edges=[edge for edge in self.dataset.edges if edge['provider']!='quizjet' or edge['rank']==1]
        self.dataset.save()
        self.attempt();self.attempt()
        self.assertEqual(RecommendationProgress.objects.count(),7)
        self.assertEqual(RecommendationProgress.objects.filter(provider='quizjet').count(),1)

    def test_quizjet_proxy_records_real_result_and_preserves_practice_context(self):
        from django.http import HttpResponse
        from django.test import RequestFactory
        from modulearn.learning.services.quizjet_tracking import process_quizjet_response
        item=self.activate()
        for answer,result in [('wrong','WRONG!'),('right','CORRECT!')]:
            request=RequestFactory().post('/proxy/http/pawscomp2.sis.pitt.edu/quizjet/EvaluateAnswer',
                {'module_id':self.target.pk,'course_instance_id':self.instance.pk,'recommendation':str(item.pk),
                 'inputans':answer,'code':'int x=1;'})
            request.user=self.student
            response=process_quizjet_response(request,'pawscomp2.sis.pitt.edu','quizjet/EvaluateAnswer',
                HttpResponse('<form><b>'+result+'</b></form>',content_type='text/html'))
            self.assertIn(str(item.pk).encode(),response.content)
        item.refresh_from_db();self.assertEqual(item.attempts,2);self.assertTrue(item.is_complete)
        self.assertEqual(list(item.events.filter(event_type='attempt').order_by('id').values_list('score',flat=True)),[0,100])
        self.assertFalse(ModuleProgress.objects.get(enrollment=self.enrollment,module=self.target).is_complete)

    def test_events_retry_idempotently_and_summary_includes_unvisited_items(self):
        item=self.activate();url=reverse('courses:recommendation_event',args=[self.instance.pk,item.pk])
        payload=json.dumps({'event_type':'visit','event_id':'retry-same-id'})
        for _ in range(2):
            self.assertEqual(self.client.post(url,payload,content_type='application/json').status_code,200)
        self.assertEqual(item.events.filter(event_type='visit').count(),1)
        self.client.force_login(self.teacher)
        response=self.client.get(reverse('courses:recommendation_logs',args=[self.instance.pk]),{'download':'summary'})
        text=b''.join(response.streaming_content).decode();self.assertIn('impressions,visits,submissions',text);self.assertIn(str(item.pk),text)

    def test_practice_scores_reject_nonfinite_values(self):
        item=self.activate();url=reverse('courses:recommendation_practice_progress',args=[self.instance.pk,item.pk])
        self.assertEqual(self.client.post(url,json.dumps({'data':[{'score':'NaN'}]}),content_type='application/json').status_code,400)
