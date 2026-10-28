import io
import json
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from courses import test_cupcake_tracking as fixtures
from courses.models import ModuleProgressEvent
from modulearn.learning.services.cupcake_tracking import record_cupcake_event, free_coding_test_score


class PartialCupcakeTests(TestCase):
    setUp = fixtures.CupcakeTests.setUp

    def check(self, passed, token='check'):
        return fixtures.envelope(kind='free-coding', identity=token, isCorrect=all(passed),
            testCasesResults=[{'title': 'Hidden' if i == 2 else 'Visible', 'passed': value}
                              for i, value in enumerate(passed)])

    def test_partial_attempt_then_completion_and_duplicate(self):
        record_cupcake_event(self.progress, self.check([True, True, False, True]))
        self.assertEqual(self.progress.progress, .75)
        self.assertEqual(self.progress.score, 75)
        self.assertFalse(self.progress.is_complete)
        self.assertFalse(self.progress.success)
        record_cupcake_event(self.progress, self.check([True, True, False, True]))
        self.assertEqual(self.progress.attempts, 1)
        record_cupcake_event(self.progress, self.check([False]*4, 'worse'))
        self.assertEqual(self.progress.progress, .75)
        self.assertEqual(self.progress.score, 0)
        record_cupcake_event(self.progress, self.check([True]*4, 'pass'))
        self.assertTrue(self.progress.is_complete)
        self.assertEqual(self.progress.score, 100)

    def test_incomplete_or_contradictory_evidence_is_not_inferred(self):
        for data in [{}, {'isCorrect':False,'testCasesResults':[]},
                     {'isCorrect':False,'testCasesResults':[{'passed':'true'}]},
                     {'isCorrect':False,'testCasesResults':[{'passed':True}]}]:
            self.assertIsNone(free_coding_test_score(data))

    def command(self, **kwargs):
        out=io.StringIO()
        call_command('backfill_cupcake_partial_progress', sessions=[self.instance.pk],
                     modules=[self.module.pk], stdout=out, **kwargs)
        return json.loads(out.getvalue())

    def historical(self):
        record_cupcake_event(self.progress, self.check([True,True,False,True]))
        self.progress.progress=0;self.progress.score=0;self.progress.save()
        self.progress.events.filter(event_type='attempt').update(score=0,progress=0)

    def test_backfill_preview_apply_idempotence_and_no_completion(self):
        self.historical()
        original_state=self.progress.state_data
        preview=self.command()
        self.assertEqual(preview['affected_activities'],1)
        self.progress.refresh_from_db();self.assertEqual(self.progress.progress,0)
        self.command(apply=True,expect_sha256=preview['sha256'])
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.progress,.75);self.assertEqual(self.progress.score,75)
        self.assertEqual(self.progress.attempts,1);self.assertFalse(self.progress.is_complete)
        self.assertEqual(self.progress.state_data,original_state)
        self.assertEqual(self.progress.events.get(event_type='attempt').score,75)
        self.assertEqual(self.progress.events.filter(source='cupcake_partial_backfill').count(),1)
        self.assertEqual(self.command()['affected_activities'],0)

    def test_backfill_stale_plan_and_malformed_history(self):
        self.historical()
        with self.assertRaises(CommandError): self.command(apply=True,expect_sha256='wrong')
        self.progress.refresh_from_db();self.assertEqual(self.progress.score,0)
        event=self.progress.events.get(event_type='attempt')
        event.payload['cupcake']['eventData']['testCasesResults'][0]['passed']='yes'
        event.save(update_fields=['payload'])
        report=self.command();self.assertEqual(report['affected_activities'],0)
        self.assertEqual(len(report['skipped']),1)

    def test_partial_practice_does_not_affect_course(self):
        from courses.models import RecommendationActivation,RecommendationProgress
        activation=RecommendationActivation.objects.create(enrollment=self.enrollment,source_module=self.module)
        practice=RecommendationProgress.objects.create(activation=activation,module=self.target,provider='cupcake',rank=1,similarity=0)
        record_cupcake_event(practice,self.check([True,True,False,True]))
        self.assertEqual(practice.progress,.75);self.assertEqual(practice.score,75)
        self.assertFalse(practice.is_complete)
        self.progress.refresh_from_db();self.assertEqual(self.progress.attempts,0)

    def test_backfill_apply_rolls_back_on_audit_failure(self):
        from unittest.mock import patch
        self.historical()
        preview=self.command()
        with patch('courses.management.commands.backfill_cupcake_partial_progress.ModuleProgressEvent.objects.create', side_effect=RuntimeError('audit failure')):
            with self.assertRaises(RuntimeError):
                self.command(apply=True,expect_sha256=preview['sha256'])
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.score,0)
        self.assertEqual(self.progress.events.get(event_type='attempt').score,0)

    def test_backfill_refuses_a_plan_after_new_attempt(self):
        self.historical()
        preview=self.command()
        record_cupcake_event(self.progress,self.check([True]*4,'new-success'))
        with self.assertRaises(CommandError):
            self.command(apply=True,expect_sha256=preview['sha256'])
        self.progress.refresh_from_db()
        self.assertTrue(self.progress.is_complete)
        self.assertEqual(self.progress.score,100)
