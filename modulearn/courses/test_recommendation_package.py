import json
from pathlib import Path
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from courses.models import Course, CourseInstance, Unit, Module, Enrollment, ModuleProgress, StaticRecommendationSet, RecommendationProgress, RecommendationEvent
from modulearn.learning.services.recommendation_package import install_package, parse_package
from modulearn.learning.services.progress import apply_progress_snapshot
from modulearn.learning.services.static_recommendations import resolve_nodes


@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class RecommendationPackageTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='package-teacher', is_instructor=True)
        self.student = User.objects.create_user(username='package-student', is_student=True)
        self.course = Course.objects.create(id='package', title='Package course')
        self.instance = CourseInstance.objects.create(course=self.course, group_name='Class')
        self.instance.instructors.add(self.teacher)
        self.unit = Unit.objects.create(course=self.course, title='Basics')
        self.source = Module.objects.create(unit=self.unit, title='Problem', content_url='https://example.org/problem')
        self.enrollment = Enrollment.objects.create(student=self.student, course_instance=self.instance)
        self.data = {'format': 'modulearn.recommendations.v1', 'activities': [
            {'id': 'problem', 'title': 'Problem', 'unit': 'Basics', 'provider': 'cupcake', 'protocols': ['splice'], 'url': self.source.content_url},
            {'id': 'example', 'title': 'Example', 'unit': 'Basics', 'provider': 'cupcake', 'protocols': ['splice'], 'url': 'https://example.org/example'}],
            'recommendations': [{'source': 'problem', 'target': 'example', 'type': 'worked_example', 'rank': 1}]}
        self.url = reverse('courses:static_recommendations', args=[self.instance.pk])

    def raw(self): return json.dumps(self.data).encode()

    def test_one_upload_enables_creates_binds_and_logs_both_contexts(self):
        self.client.force_login(self.teacher)
        response = self.client.post(self.url, {'action': 'upload', 'files': SimpleUploadedFile('ready.json', self.raw())}, follow=True)
        self.assertContains(response, 'Recommendations ready: 2 activities, 1 links.')
        target = Module.objects.get(title='Example'); self.assertTrue(target.is_recommendation_only)
        self.assertEqual(Module.objects.filter(title='Problem').count(), 1)
        self.assertFalse(resolve_nodes(StaticRecommendationSet.objects.get(course=self.course), self.course)[1])
        progress = ModuleProgress.objects.get(module=self.source, enrollment=self.enrollment)
        apply_progress_snapshot(progress, source='pcrs', score=0, success=False, payload={'pcrs_result': {'score': 0, 'max_score': 1}})
        practice = RecommendationProgress.objects.get(module=target)
        apply_progress_snapshot(practice, source='splice', score=100, progress=1, is_complete=True)
        progress.refresh_from_db(); self.assertEqual(progress.score, 0)
        self.assertFalse(ModuleProgress.objects.filter(module=target).exists())
        logs = reverse('courses:recommendation_logs', args=[self.instance.pk])
        self.assertContains(self.client.get(logs), 'Normal course activity')
        for export in ['course_csv', 'csv', 'summary']:
            response = self.client.get(logs, {'download': export, 'q': self.student.username})
            text = b''.join(response.streaming_content).decode()
            self.assertIn(self.student.username, text)
            self.assertIn('Problem', text)
        self.assertEqual(LogEntry.objects.count(), 1)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(logs, {'download': 'course_csv'}).status_code, 403)

    def test_repeat_upload_preserves_practice_and_course_history(self):
        install_package(self.course.pk, self.raw(), actor=self.teacher)
        progress = ModuleProgress.objects.get(module=self.source, enrollment=self.enrollment)
        apply_progress_snapshot(progress, source='pcrs', score=0, success=False, payload={'pcrs_result': {'score': 0, 'max_score': 1}})
        item = RecommendationProgress.objects.get(); item.score=83; item.feedback='up'; item.save()
        before = list(ModuleProgress.objects.values())
        report = install_package(self.course.pk, self.raw(), actor=self.teacher)
        self.assertTrue(report['unchanged']); self.assertEqual(report['assignments_changed'], 0)
        self.assertEqual(Module.objects.count(), 2)
        item.refresh_from_db(); self.assertEqual((item.score, item.feedback), (83, 'up'))
        self.assertEqual(list(ModuleProgress.objects.values()), before)
        self.data['activities'][1]['url']='https://example.org/new-example'
        self.data['activities'][1]['title']='Replacement'
        install_package(self.course.pk, self.raw(), actor=self.teacher)
        item.refresh_from_db(); self.assertIsNotNone(item.retired_at); self.assertEqual(item.score,83)
        self.assertTrue(RecommendationEvent.objects.filter(event_type='dataset_transition').exists())

    def test_atomic_rollback_on_late_failure_and_identity_conflict(self):
        with patch('modulearn.learning.services.recommendation_package.transition_recommendations', side_effect=ValueError('stop')):
            with self.assertRaises(ValueError): install_package(self.course.pk, self.raw(), actor=self.teacher)
        self.assertEqual(Module.objects.count(), 1); self.assertFalse(StaticRecommendationSet.objects.exists())
        Module.objects.create(unit=self.unit, title='Example', content_url='https://example.org/other')
        with self.assertRaises(ValueError): install_package(self.course.pk, self.raw(), actor=self.teacher)
        self.assertFalse(StaticRecommendationSet.objects.exists()); self.assertFalse(LogEntry.objects.exists())

    def test_invalid_links_duplicate_urls_and_locked_courses(self):
        self.data['recommendations'][0]['target']='missing'
        with self.assertRaises(ValueError): parse_package(self.raw())
        self.data['recommendations'][0]['target']='example'
        self.data['activities'][1]['url']=self.source.content_url
        with self.assertRaises(ValueError): parse_package(self.raw())
        self.data['activities'][1]['url']='https://example.org/example'
        self.course.is_locked_for_research=True; self.course.save()
        with self.assertRaises(ValueError): install_package(self.course.pk, self.raw(), actor=self.teacher)

    def test_missing_original_is_added_as_coursework(self):
        self.data['activities'][0].update(url='https://example.org/new-problem', title='New problem', unit='New unit')
        install_package(self.course.pk, self.raw(), actor=self.teacher)
        self.assertFalse(Module.objects.get(title='New problem').is_recommendation_only)
        self.assertTrue(Module.objects.get(title='Example').is_recommendation_only)

    def test_cs007_artifact_installs_without_local_ids_or_manual_bindings(self):
        raw=(Path(__file__).resolve().parents[2]/'ML_Recs/2026-10-11/CS007.recommendations.json').read_bytes()
        report=install_package(self.course.pk, raw, actor=self.teacher)
        self.assertEqual((report['activities'], report['links']), (247,684))
        dataset=StaticRecommendationSet.objects.get(course=self.course)
        self.assertFalse(resolve_nodes(dataset,self.course)[1])
        self.assertEqual(Module.objects.filter(unit__course=self.course,is_recommendation_only=False).count(),115)
        self.assertEqual(install_package(self.course.pk,raw,actor=self.teacher)['created_modules'],[])
