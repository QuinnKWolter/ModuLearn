import hashlib
import json
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import TestCase, RequestFactory

from accounts.models import User
from courses.models import Course, Unit, Module, CourseInstance, Enrollment, StaticRecommendationSet, RecommendationActivation, RecommendationProgress, RecommendationEvent, ModuleProgress
from courses.test_static_recommendations import rec_file
from modulearn.learning.services.static_recommendations import parse_uploads
from modulearn.learning.services.unit_import import import_unit_package
from modulearn.learning.services.recommendation_rollout import transition_recommendations
from modulearn.learning.services.recommendation_tracking import practice_items, practice_for_request, apply_practice_snapshot


class UnitRolloutTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(id='rollout', title='Existing course')
        self.unit = Unit.objects.create(course=self.course, title='Existing unit', order=50)
        self.existing = Module.objects.create(unit=self.unit, title='Keep this')
        self.package = {'format': 'modulearn.unit.v1', 'ready': True, 'unit': {
            'title': 'Arrays of Objects', 'modules': [{'title': 'New example', 'provider_id': 'pcex',
            'content_url': 'https://example.org/activity', 'supported_protocols': ['splice']}]}}

    def raw(self):
        return json.dumps(self.package).encode()

    def test_dry_run_apply_and_idempotency_preserve_existing_course(self):
        raw = self.raw()
        plan = import_unit_package(self.course.pk, raw)
        self.assertEqual(Unit.objects.count(), 1)
        import_unit_package(self.course.pk, raw, apply=True, expected_sha256=plan['sha256'])
        self.assertEqual(Unit.objects.count(), 2)
        self.assertEqual(Module.objects.count(), 2)
        self.assertEqual(Unit.objects.get(title='Arrays of Objects').order, 60)
        self.existing.refresh_from_db();self.assertEqual(self.existing.title, 'Keep this')
        self.course.refresh_from_db();self.assertEqual(self.course.title, 'Existing course')
        self.assertEqual(import_unit_package(self.course.pk, raw)['action'], 'already_present')
        self.package['unit']['modules'][0]['content_url'] = 'https://example.org/changed'
        with self.assertRaises(ValueError):
            import_unit_package(self.course.pk, self.raw(), apply=True, expected_sha256=hashlib.sha256(self.raw()).hexdigest())

    def test_rejects_placeholder_urls_unreviewed_and_locked_packages(self):
        raw = self.raw()
        with self.assertRaises(ValueError):
            import_unit_package(self.course.pk, raw, apply=True, expected_sha256='wrong')
        self.package['ready'] = False
        with self.assertRaises(ValueError):import_unit_package(self.course.pk, self.raw())
        self.package['ready'] = True
        self.package['unit']['modules'][0]['content_url'] = ''
        with self.assertRaises(ValueError):import_unit_package(self.course.pk, self.raw())
        self.course.is_locked_for_research=True;self.course.save()
        with self.assertRaises(ValueError):import_unit_package(self.course.pk, raw)
        self.assertEqual(Unit.objects.count(), 1)

    def test_failure_rolls_back_entire_unit(self):
        raw=self.raw()
        with patch.object(Module.objects, 'create', side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):
                import_unit_package(self.course.pk, raw, apply=True, expected_sha256=hashlib.sha256(raw).hexdigest())
        self.assertEqual(Unit.objects.count(), 1)

    def test_recommendation_only_import_excludes_course_credit_and_normal_access(self):
        from modulearn.learning.services.access_rules import evaluate_module_access
        from modulearn.learning.services.progress import recompute_course_progress
        from modulearn.learning.services.recommendation_tracking import select_candidates
        self.package['unit']['modules'][0]['is_recommendation_only'] = True
        raw = self.raw()
        import_unit_package(self.course.pk, raw, apply=True, expected_sha256=hashlib.sha256(raw).hexdigest())
        target = Module.objects.get(title='New example')
        student = User.objects.create_user(username='practice-scope')
        instance = CourseInstance.objects.create(course=self.course, group_name='Scope test')
        enrollment = Enrollment.objects.create(student=student, course_instance=instance)
        self.assertFalse(evaluate_module_access(target, enrollment).can_access)
        self.assertFalse(ModuleProgress.objects.filter(enrollment=enrollment, module=target).exists())
        summary = recompute_course_progress(enrollment)
        self.assertEqual(summary.total_modules, 1)
        dataset = StaticRecommendationSet(options={'limit': 2})
        edge = {'target': 'practice', 'provider': 'pcex', 'rank': 1, 'similarity': .9}
        self.assertEqual(select_candidates(dataset, {'practice': target}, [edge], self.existing.pk), [(target, edge)])


class RecommendationRolloutTests(TestCase):
    def setUp(self):
        self.course=Course.objects.create(id='recs-rollout',title='Course',plugin_config={'plugins':{'static_recommendations':{'enabled':True}}})
        unit=Unit.objects.create(course=self.course,title='Basics')
        self.source=Module.objects.create(unit=unit,title='Challenge',provider_id='pcex_ch')
        self.target=Module.objects.create(unit=unit,title='Example',provider_id='pcex')
        self.retired=Module.objects.create(unit=unit,title='Old target',provider_id='quizjet')
        self.student=User.objects.create_user(username='rollout-student')
        instance=CourseInstance.objects.create(course=self.course,group_name='demo')
        self.enrollment=Enrollment.objects.create(student=self.student,course_instance=instance)
        from django.utils import timezone
        self.activation=RecommendationActivation.objects.create(enrollment=self.enrollment,source_module=self.source,activated_at=timezone.now(),failures=2)
        self.old=RecommendationProgress.objects.create(activation=self.activation,module=self.retired,provider='quizjet',rank=1,similarity=.7,score=100,is_complete=True,feedback='up')
        self.event=RecommendationEvent.objects.create(activation=self.activation,recommendation=self.old,event_type='completion',score=100)
        self.dataset=StaticRecommendationSet.objects.create(course=self.course,**parse_uploads([rec_file()]))

    def test_transition_preserves_history_and_rejects_retired_launches(self):
        baseline=list(ModuleProgress.objects.values('id','score','progress','is_complete','attempts'))
        plan=transition_recommendations(self.course.pk)
        self.assertEqual((plan['add'],plan['retire']),(1,1))
        self.old.refresh_from_db();self.assertIsNone(self.old.retired_at)
        transition_recommendations(self.course.pk,apply=True,expected_plan=plan['plan_sha256'])
        self.old.refresh_from_db();self.assertIsNotNone(self.old.retired_at)
        self.assertEqual((self.old.score,self.old.is_complete,self.old.feedback),(100,True,'up'))
        self.assertTrue(RecommendationEvent.objects.filter(pk=self.event.pk).exists())
        self.assertEqual([i['module_id'] for i in practice_items(self.enrollment)],[self.target.pk])
        req=RequestFactory().get('/');req.user=self.student
        with self.assertRaises(PermissionDenied):practice_for_request(req,token=str(self.old.pk))
        with self.assertRaises(PermissionDenied):apply_practice_snapshot(self.old,source='splice',score=0)
        self.assertEqual(list(ModuleProgress.objects.values('id','score','progress','is_complete','attempts')),baseline)
        self.assertEqual(transition_recommendations(self.course.pk)['assignments_changed'],0)
        self.assertEqual(RecommendationEvent.objects.filter(event_type='dataset_transition').count(),1)

    def test_stale_plan_and_unresolved_graph_fail_without_changes(self):
        plan=transition_recommendations(self.course.pk)
        self.dataset.options={'limit':1};self.dataset.save()
        with self.assertRaises(ValueError):transition_recommendations(self.course.pk,apply=True,expected_plan=plan['plan_sha256'])
        self.target.delete()
        with self.assertRaises(ValueError):transition_recommendations(self.course.pk)
        self.old.refresh_from_db();self.assertIsNone(self.old.retired_at)

    def test_transition_rolls_back_if_audit_write_fails(self):
        plan=transition_recommendations(self.course.pk)
        with patch.object(RecommendationEvent.objects,'create',side_effect=RuntimeError('audit failure')):
            with self.assertRaises(RuntimeError):
                transition_recommendations(self.course.pk,apply=True,expected_plan=plan['plan_sha256'])
        self.old.refresh_from_db();self.assertIsNone(self.old.retired_at)
        self.assertEqual(RecommendationProgress.objects.count(),1)

    def test_retained_and_restored_practice_keeps_score_and_feedback(self):
        key=self.dataset.edges[0]['target']
        self.dataset.bindings[key]=self.retired.pk;self.dataset.save()
        plan=transition_recommendations(self.course.pk)
        self.assertEqual(plan['retain'],1)
        transition_recommendations(self.course.pk,apply=True,expected_plan=plan['plan_sha256'])
        self.old.refresh_from_db();self.assertEqual(self.old.score,100);self.assertEqual(self.old.feedback,'up')
        self.dataset.bindings={};self.dataset.save()
        plan=transition_recommendations(self.course.pk);transition_recommendations(self.course.pk,apply=True,expected_plan=plan['plan_sha256'])
        self.dataset.bindings[key]=self.retired.pk;self.dataset.save()
        plan=transition_recommendations(self.course.pk);self.assertEqual(plan['restore'],1)
        transition_recommendations(self.course.pk,apply=True,expected_plan=plan['plan_sha256'])
        self.old.refresh_from_db();self.assertIsNone(self.old.retired_at);self.assertEqual(self.old.score,100)
