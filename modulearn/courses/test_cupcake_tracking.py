from django.test import TestCase
from django.urls import reverse
from accounts.models import User
from courses.models import Course, Unit, Module, CourseInstance, Enrollment, ModuleProgress, ModuleProgressEvent, RecommendationActivation, RecommendationProgress, StaticRecommendationSet
from courses.test_static_recommendations import parse_uploads, rec_file
from modulearn.learning.services.cupcake_tracking import record_cupcake_event


def envelope(name='answerChecked', kind='code-completion', identity='event-1', **data):
    return {'event_id':identity,'message':{'type':'cupcake:log','eventName':name,'activityType':kind,'activityId':'test-activity','eventData':data,'clientTimestamp':12345}}


class CupcakeTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='cupcake-student',is_student=True)
        self.course=Course.objects.create(id='cupcake-test',title='Test',plugin_config={'plugins':{'static_recommendations':{'enabled':True}}})
        unit=Unit.objects.create(course=self.course,title='Basics')
        self.module=Module.objects.create(unit=unit,title='Challenge',provider_id='pcex_ch')
        self.target=Module.objects.create(unit=unit,title='Example',provider_id='pcex')
        self.instance=CourseInstance.objects.create(course=self.course,group_name='Test')
        self.enrollment=Enrollment.objects.create(student=self.user,course_instance=self.instance)
        self.progress=ModuleProgress.objects.get(enrollment=self.enrollment,module=self.module)
        self.client.force_login(self.user)

    def test_failed_checks_count_once_and_activate_recommendations(self):
        StaticRecommendationSet.objects.create(course=self.course,course_instance=self.instance,**parse_uploads([rec_file()]))
        first=envelope(isCorrect=False,blanksSucceededPercent=33.33,blanksStates=[{'choice':'wrong'}])
        record_cupcake_event(self.progress,first);record_cupcake_event(self.progress,first)
        self.assertEqual(self.progress.attempts,1)
        record_cupcake_event(self.progress,envelope(identity='event-2',isCorrect=False,blanksSucceededPercent=66.67))
        self.assertEqual(RecommendationActivation.objects.get().failures,2)
        self.assertEqual(RecommendationProgress.objects.count(),1)
        record_cupcake_event(self.progress,envelope(identity='event-3',isCorrect=True,blanksSucceededPercent=100))
        self.assertEqual(self.progress.attempts,3);self.assertTrue(self.progress.is_complete)
        self.assertEqual(list(ModuleProgressEvent.objects.filter(event_type='attempt').order_by('id').values_list('score',flat=True)),[33.33,66.67,100])

    def test_worked_example_viewing_completes_without_fabricating_grade_or_attempt(self):
        for identity,percent in [('one',40),('two',100)]:
            record_cupcake_event(self.progress,envelope('explanationOpened','worked-example',identity,progress={'snippets':100,'explanations':percent}))
        self.assertTrue(self.progress.is_complete);self.assertIsNone(self.progress.score);self.assertEqual(self.progress.attempts,0)

    def test_practice_isolation_and_tracing_completion(self):
        StaticRecommendationSet.objects.create(course=self.course, course_instance=self.instance)
        a=RecommendationActivation.objects.create(enrollment=self.enrollment,source_module=self.module)
        practice=RecommendationProgress.objects.create(activation=a,module=self.target,provider='quizjet',rank=1,similarity=.9)
        baseline=list(ModuleProgress.objects.values('id','score','progress','attempts'))
        url=reverse('courses:recommendation_practice_progress',args=[self.instance.pk,practice.pk])
        for key,correct in [('wrong',False),('correct',True)]:
            response=self.client.post(url,{'provider_event':envelope(kind='parameterized-code-tracing',identity=key,isCorrect=correct,answer='test',parameters=[])},content_type='application/json')
            self.assertEqual(response.status_code,200)
        practice.refresh_from_db();self.assertEqual(practice.attempts,2);self.assertTrue(practice.is_complete)
        self.assertEqual(list(ModuleProgress.objects.values('id','score','progress','attempts')),baseline)
        self.assertEqual(practice.events.filter(event_type='completion').count(),1)

    def test_unknown_and_interaction_events_log_without_changing_scores(self):
        record_cupcake_event(self.progress,envelope('choiceSelected',snippet='a choice'))
        record_cupcake_event(self.progress,envelope('grade','future-player','new',score=1))
        self.assertEqual(self.progress.attempts,0);self.assertIsNone(self.progress.score)
        self.assertEqual(ModuleProgressEvent.objects.filter(event_type='provider_event').count(),2)

    def test_free_coding_checks_track_attempts_and_activate_recommendations(self):
        StaticRecommendationSet.objects.create(course=self.course, course_instance=self.instance,
            **parse_uploads([rec_file()]))
        for identity, correct in [('failed', False), ('passed', True)]:
            data = envelope(kind='free-coding', identity=identity, isCorrect=correct,
                isPassed=correct, testCasesResults=[{'title': 'Hidden test', 'passed': correct}])
            record_cupcake_event(self.progress, data)
            record_cupcake_event(self.progress, data)
        # runResultReceived accompanies answerChecked; it must not count twice.
        record_cupcake_event(self.progress, envelope('runResultReceived', 'free-coding', 'run',
            testCasesResults=[{'passed': True}]))
        self.assertEqual(self.progress.attempts, 2)
        self.assertTrue(self.progress.is_complete)
        self.assertEqual(self.progress.score, 100)
        self.assertEqual(RecommendationActivation.objects.get().failures, 1)
        self.assertEqual(list(self.progress.events.filter(event_type='attempt').order_by('id')
            .values_list('score', flat=True)), [0, 100])
        self.assertEqual(self.progress.events.filter(event_type='provider_event').count(), 3)
        self.assertIn('testCasesResults', self.progress.last_response)

    def test_free_coding_practice_completion_is_separate_from_course_credit(self):
        from unittest.mock import patch
        from courses.models import CourseProgress
        StaticRecommendationSet.objects.create(course=self.course, course_instance=self.instance)
        activation = RecommendationActivation.objects.create(enrollment=self.enrollment, source_module=self.module)
        practice = RecommendationProgress.objects.create(activation=activation, module=self.target,
            provider='cupcake', rank=1, similarity=.9)
        before = list(ModuleProgress.objects.order_by('id').values())
        totals = list(CourseProgress.objects.values())
        with patch.object(CourseProgress, 'submit_grade_to_canvas') as submit:
            for identity, correct in [('wrong', False), ('right', True)]:
                event = envelope(kind='free-coding', identity=identity, isCorrect=correct,
                    isPassed=correct, testCasesResults=[{'passed': correct}])
                record_cupcake_event(practice, event)
                record_cupcake_event(practice, event)
            submit.assert_not_called()
        self.assertEqual(practice.attempts, 2)
        self.assertTrue(practice.is_complete)
        self.assertEqual(list(practice.events.filter(event_type='attempt').order_by('id')
            .values_list('score', flat=True)), [0, 100])
        self.assertEqual(before, list(ModuleProgress.objects.order_by('id').values()))
        self.assertEqual(totals, list(CourseProgress.objects.values()))

    def test_historical_free_coding_repair_preview_apply_and_repeat(self):
        import json
        from io import StringIO
        from unittest.mock import patch
        from datetime import timedelta
        from django.core.management import call_command
        from django.utils import timezone
        from courses.models import CourseProgress
        when = timezone.now() - timedelta(days=2)
        raw_ids = []
        for identity, correct in [('old-wrong', False), ('old-right', True)]:
            event = ModuleProgressEvent.objects.create(module_progress=self.progress, user=self.user,
                module=self.module, course_instance=self.instance, event_type='provider_event', source='cupcake',
                payload={'transport_id': identity, 'cupcake': envelope(kind='free-coding',
                    identity=identity, isCorrect=correct, isPassed=correct)['message']})
            ModuleProgressEvent.objects.filter(pk=event.pk).update(created_at=when)
            raw_ids.append(event.pk)
        def run(apply=False):
            out = StringIO()
            call_command('repair_cupcake_progress', sessions=[self.instance.pk], modules=[self.module.pk],
                apply=apply, stdout=out)
            return json.loads(out.getvalue())
        before = list(ModuleProgress.objects.values())
        totals = list(CourseProgress.objects.values())
        events = list(ModuleProgressEvent.objects.order_by('id').values())
        preview = run()
        self.assertEqual(preview['restored_attempts'], 2)
        self.assertEqual(preview['new_completions'], 1)
        self.assertEqual(before, list(ModuleProgress.objects.values()))
        self.assertEqual(totals, list(CourseProgress.objects.values()))
        self.assertEqual(events, list(ModuleProgressEvent.objects.order_by('id').values()))
        with patch.object(CourseProgress, 'submit_grade_to_canvas') as submit:
            applied = run(True)
            submit.assert_not_called()
        self.assertEqual(applied['changes'], preview['changes'])
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.attempts, 2)
        self.assertTrue(self.progress.is_complete)
        self.assertEqual(self.progress.score, 100)
        self.assertEqual(self.progress.completed_at, when)
        self.assertEqual(CourseProgress.objects.get(enrollment=self.enrollment).modules_completed, 1)
        self.assertEqual(list(self.progress.events.filter(event_type='attempt').order_by('id')
            .values_list('score', flat=True)), [0, 100])
        self.assertEqual(list(ModuleProgressEvent.objects.filter(pk__in=raw_ids).order_by('id').values()), events)
        self.assertEqual(run(True)['restored_attempts'], 0)
        # Transport retries of original events cannot create new attempts after repair.
        record_cupcake_event(self.progress, envelope(kind='free-coding', identity='old-right', isCorrect=True))
        self.assertEqual(self.progress.attempts, 2)

    def test_historical_repair_skips_ambiguous_existing_attempts(self):
        import json
        from io import StringIO
        from django.core.management import call_command
        self.progress.attempts = 1
        self.progress.save()
        ModuleProgressEvent.objects.create(module_progress=self.progress, user=self.user,
            module=self.module, course_instance=self.instance, event_type='provider_event', source='cupcake',
            payload={'transport_id': 'old', 'cupcake': envelope(kind='free-coding', isCorrect=True)['message']})
        out = StringIO()
        call_command('repair_cupcake_progress', sessions=[self.instance.pk], modules=[self.module.pk], apply=True, stdout=out)
        result = json.loads(out.getvalue())
        self.assertEqual(result['restored_attempts'], 0)
        self.assertEqual(len(result['skipped']), 1)
        self.progress.refresh_from_db()
        self.assertFalse(self.progress.is_complete)

    def test_historical_repair_failure_rolls_back_all_writes(self):
        from io import StringIO
        from unittest.mock import patch
        from django.core.management import call_command
        event = ModuleProgressEvent.objects.create(module_progress=self.progress, user=self.user,
            module=self.module, course_instance=self.instance, event_type='provider_event', source='cupcake',
            payload={'transport_id': 'old', 'cupcake': envelope(kind='free-coding', isCorrect=True)['message']})
        with patch('courses.management.commands.repair_cupcake_progress.recompute_course_progress',
                side_effect=RuntimeError('Simulated failure')), self.assertRaises(RuntimeError):
            call_command('repair_cupcake_progress', sessions=[self.instance.pk], modules=[self.module.pk],
                apply=True, stdout=StringIO())
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.attempts, 0)
        self.assertFalse(self.progress.is_complete)
        self.assertEqual(list(self.progress.events.values_list('id', flat=True)), [event.pk])

    def test_bad_score_is_rejected_before_any_writes(self):
        for score in [float('nan'),float('inf'),-1,101,'100',True]:
            with self.subTest(score=score),self.assertRaises(ValueError):
                record_cupcake_event(self.progress,envelope(isCorrect=False,blanksSucceededPercent=score))
        self.assertFalse(ModuleProgressEvent.objects.exists())

    def test_no_resubmission_policy_logs_checks_without_overwriting_grade(self):
        self.module.allow_resubmission=False;self.module.save()
        record_cupcake_event(self.progress,envelope(isCorrect=False,blanksSucceededPercent=0))
        record_cupcake_event(self.progress,envelope(identity='second',isCorrect=True,blanksSucceededPercent=100))
        self.assertEqual(self.progress.score,0);self.assertEqual(self.progress.attempts,1)
        self.assertEqual(ModuleProgressEvent.objects.filter(event_type='provider_event').count(),2)

    def test_observed_browser_events_replay_in_course_and_practice_contexts(self):
        import json
        from pathlib import Path
        events=json.loads((Path(__file__).parent/'fixtures/cupcake_observed_events.json').read_text())
        for kind in ['worked-example','code-completion','parameterized-code-tracing']:
            for practice in [False,True]:
                with self.subTest(kind=kind,practice=practice):
                    module=Module.objects.create(unit=self.module.unit,title=f'{kind}-{practice}')
                    normal,_=ModuleProgress.get_or_create_progress(user=self.user,module=module,course_instance=self.instance)
                    if practice:
                        activation,_=RecommendationActivation.objects.get_or_create(enrollment=self.enrollment,source_module=self.module)
                        progress=RecommendationProgress.objects.create(activation=activation,module=module,provider='cupcake',rank=1,similarity=.8)
                    else:
                        progress=normal
                    relevant=[e for e in events if e['message']['activityType']==kind]
                    for event in relevant:
                        record_cupcake_event(progress,event)
                        record_cupcake_event(progress,event)  # Retry must be harmless.
                    self.assertEqual(progress.attempts,0 if kind=='worked-example' else 2)
                    self.assertEqual(progress.is_complete,kind!='parameterized-code-tracing')
                    if kind=='code-completion':self.assertEqual(progress.score,100)
                    if practice:
                        normal=ModuleProgress.objects.get(enrollment=self.enrollment,module=module)
                        self.assertEqual(normal.attempts,0);self.assertFalse(normal.is_complete)
                    logs=progress.events
                    self.assertEqual(logs.filter(event_type='provider_event').count(),len(relevant))
