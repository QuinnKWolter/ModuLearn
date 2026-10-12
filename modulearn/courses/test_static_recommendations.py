import csv
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from courses.models import Course, CourseInstance, Enrollment, Module, ModuleAccessLog, ModuleProgress, StaticRecommendationSet, Unit
from modulearn.learning.services.static_recommendations import parse_uploads, recommendations_for, resolve_nodes
from modulearn.learning.services.progress import apply_progress_snapshot


def upload(name, rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return SimpleUploadedFile(name, stream.getvalue().encode('utf-8-sig'))


def rec_file(**changes):
    return upload('CS007_recommendations_top3_wide.csv', [{
        'query_item': 'Challenge', 'query_provider': 'pcex_ch', 'query_topic': 'Basics', 'query_code': 'int n = 1;\nreturn n;',
        'pcex_rank_1_item': 'Example', 'pcex_rank_1_code': 'int n = 2;', 'pcex_rank_1_similarity': '0.8', **changes,
    }])


def assignment_file(cluster='0', prefix='CS007'):
    return upload(prefix + '_kc_assignments.csv', [
        {'SubjectID': 'course:0001', 'item_name': title, 'provider_id': provider, 'topic_name': 'Basics',
         'kc_cluster': cluster, 'attention': '0.1', 'subtree_vector': '[1, 2]', 'Score': '0'}
        for title, provider in [('Challenge', 'pcex_ch'), ('Example', 'pcex')]
    ])


def medoid_file(cluster='0'):
    return upload('CS007_kc_assignments_kc_medoids.csv', [{'kc_cluster': cluster, 'raw_pattern': 'x', 'normalized_pattern': 'variable', 'subtree_code': ''}])


class RecommendationImportTests(SimpleTestCase):
    def test_full_set_preserves_analysis_and_multiline_code(self):
        data = parse_uploads([rec_file(), assignment_file(), medoid_file()])
        self.assertEqual(len(data['nodes']), 2)
        self.assertEqual(data['edges'][0]['similarity'], .8)
        self.assertEqual(data['analysis']['assignments'][0]['subtree_vector'], '[1, 2]')
        self.assertEqual(data['analysis']['recommendations'][0]['query_code'], 'int n = 1;\nreturn n;')
        self.assertEqual(data['nodes'][data['edges'][0]['target']]['clusters'], ['0'])

    def test_recommendations_alone_and_empty_slots_supported(self):
        data = parse_uploads([rec_file(quizjet_rank_1_item='', quizjet_rank_1_similarity='')])
        self.assertEqual(len(data['edges']), 1)

    def test_same_name_different_code_targets_remain_distinct_and_stable(self):
        rows = [dict(query_item='Question '+str(n), query_provider='pcrs', query_topic='Basics',
                     quizjet_rank_1_item='Comparing Strings', quizjet_rank_1_code=code,
                     quizjet_rank_1_similarity='.8')
                for n, code in enumerate(['String x="A";', 'String x="a";', 'String x="A";'])]
        first = parse_uploads([upload('recs.csv', rows)])
        keys = [edge['target'] for edge in first['edges']]
        self.assertEqual(keys[0], keys[2])
        self.assertNotEqual(keys[0], keys[1])
        self.assertEqual(first['analysis']['code'][keys[0]], 'String x="A";')
        second = parse_uploads([upload('recs.csv', rows[::-1])])
        self.assertEqual(set(first['nodes']), set(second['nodes']))

    def test_rejects_invalid_similarity_and_rank(self):
        for value in ('NaN', 'inf', '1.2', ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_uploads([rec_file(pcex_rank_1_similarity=value)])
        with self.assertRaises(ValueError):
            parse_uploads([rec_file(pcex_rank_0_item='Example', pcex_rank_0_similarity='.1')])

    def test_rejects_mixed_course_cluster_mismatch_and_duplicate_file_kinds(self):
        for files in ([rec_file(), assignment_file(prefix='CMPINF0401')],
                      [rec_file(), assignment_file(), medoid_file('1')],
                      [rec_file(), rec_file()], [assignment_file()]):
            with self.subTest(files=[f.name for f in files]), self.assertRaises(ValueError):
                parse_uploads(files)

    def test_rejects_missing_assignment_activity_and_malformed_rows(self):
        with self.assertRaises(ValueError):
            parse_uploads([rec_file(query_item='Not in assignments'), assignment_file()])
        with self.assertRaises(ValueError):
            parse_uploads([SimpleUploadedFile('bad.csv', b'query_item,query_provider,query_topic\nmissing\n')])


@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class RecommendationWorkflowTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='recs-teacher', is_instructor=True)
        self.student = User.objects.create_user(username='recs-student', is_student=True)
        self.course = Course.objects.create(id='recs-course', title='Recommendations', plugin_config={'plugins': {'static_recommendations': {'enabled': True}}})
        self.course.instructors.add(self.teacher)
        self.instance = CourseInstance.objects.create(course=self.course, group_name='Session')
        self.instance.instructors.add(self.teacher)
        self.unit = Unit.objects.create(course=self.course, title='Basics')
        self.source = Module.objects.create(unit=self.unit, title='Challenge', provider_id='pcex_ch')
        self.target = Module.objects.create(unit=self.unit, title='Example', provider_id='pcex')
        self.enrollment = Enrollment.objects.create(student=self.student, course_instance=self.instance)
        self.dataset = StaticRecommendationSet.objects.create(course=self.course,course_instance=self.instance, **parse_uploads([rec_file(), assignment_file(), medoid_file()]))
        self.manage = reverse('courses:static_recommendations', args=[self.instance.pk])
        self.queue = reverse('courses:recommendation_queue', args=[self.instance.pk])
        self.click = reverse('courses:recommended_module', args=[self.instance.pk, self.target.pk])
        self.client.force_login(self.teacher)

    def complete(self, module):
        progress, _ = ModuleProgress.objects.get_or_create(user=self.student, enrollment=self.enrollment, module=module)
        apply_progress_snapshot(progress, progress=1, success=True, source='test', event_type='completion')
        return progress

    def test_practice_library_creates_matches_and_edits_without_course_configuration(self):
        key = self.dataset.edges[0]['target']
        response = self.client.post(self.manage, {'action': 'binding', 'revision': self.dataset.updated_at.isoformat(),
            'node': key, 'module': '0', 'new_content_url': 'https://example.org/practice'})
        self.assertEqual(response.status_code, 302)
        self.dataset.refresh_from_db()
        module = Module.objects.get(pk=self.dataset.bindings[key])
        self.assertTrue(module.is_recommendation_only)
        from courses.views import _module_rule_context
        self.assertNotIn(module.pk, [m.pk for g in _module_rule_context(self.course) for m in g['modules']])
        self.client.post(self.manage, {'action': 'practice', 'revision': self.dataset.updated_at.isoformat(),
            'module': module.pk, 'content_url': 'https://example.org/updated', 'visible': 'on'})
        self.dataset.refresh_from_db()
        module = Module.objects.get(pk=self.dataset.bindings[key])
        self.assertEqual(module.content_url, 'https://example.org/updated')
        self.assertTrue(module.is_visible)

    def test_variant_needs_explicit_binding_even_with_single_title_match(self):
        key = self.dataset.edges[0]['target']
        self.dataset.nodes[key]['code_variant'] = 'example-variant'
        resolved, issues, _ = resolve_nodes(self.dataset, self.course)
        self.assertNotIn(key, resolved)
        self.assertTrue(any(issue['key'] == key for issue in issues))
        self.dataset.bindings[key] = self.target.pk
        resolved, _, _ = resolve_nodes(self.dataset, self.course)
        self.assertEqual(resolved[key], self.target)

    def fail_twice(self):
        progress = ModuleProgress.objects.get(user=self.student, enrollment=self.enrollment, module=self.source)
        for _ in range(2):
            apply_progress_snapshot(progress, source='pcrs', score=0, success=False,
                payload={'pcrs_result': {'score': 0, 'max_score': 1}})

    def test_upload_render_download_and_enable(self):
        self.assertEqual(self.client.get(self.manage).status_code, 200)
        response = self.client.post(self.manage, {'action': 'upload', 'files': [rec_file(), assignment_file(), medoid_file()]}, follow=True)
        self.assertContains(response, 'Recommendation files imported')
        self.dataset.refresh_from_db()
        response = self.client.post(self.manage, {'action': 'settings', 'revision': self.dataset.updated_at.isoformat(), 'enabled': 'on', 'limit': '5', 'trigger': 'completed'}, follow=True)
        self.assertContains(response, 'settings saved')
        self.assertEqual(self.client.get(self.manage, {'download': '1'}).json()['options']['limit'], 5)

    def test_invalid_upload_and_stale_settings_preserve_existing_data(self):
        old = self.dataset.updated_at
        self.client.post(self.manage, {'action': 'upload', 'files': [rec_file(pcex_rank_1_similarity='nan')]})
        self.client.post(self.manage, {'action': 'settings', 'revision': 'outdated', 'limit': '2'})
        self.dataset.refresh_from_db()
        self.assertEqual(self.dataset.updated_at, old)

    def test_students_and_unassigned_instructors_cannot_manage_or_download(self):
        outsider = User.objects.create_user(username='outsider', is_instructor=True)
        for user in (self.student, outsider):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.manage, {'download': '1'}).status_code, 403)
            self.assertEqual(self.client.post(self.manage, {'action': 'upload', 'files': [rec_file()]}).status_code, 403)

    def test_queue_retains_practice_after_course_completion(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.queue).json()['items'], [])
        self.fail_twice()
        items = self.client.get(self.queue).json()['items']
        self.assertEqual([r['module_id'] for r in items], [self.target.pk])
        self.assertIn('/practice/', items[0]['url'])
        self.complete(self.target)
        self.assertEqual(len(self.client.get(self.queue).json()['items']), 1)
        self.assertRedirects(self.client.get(self.click), reverse('courses:course_detail', args=[self.instance.pk]), fetch_redirect_response=False)

    def test_hidden_targets_are_excluded_when_assigning_practice(self):
        self.target.is_visible = False
        self.target.save()
        self.fail_twice()
        self.assertEqual(recommendations_for(self.enrollment), [])

    def test_disabled_plugin_and_other_enrollment_receive_no_recommendations(self):
        self.fail_twice()
        other_instance = CourseInstance.objects.create(course=self.course, group_name='Other session')
        other = Enrollment.objects.create(student=self.student, course_instance=other_instance)
        self.assertEqual(recommendations_for(other), [])
        self.dataset.enabled = False
        self.dataset.save()
        self.enrollment.course_instance.course = self.course
        self.assertEqual(recommendations_for(self.enrollment), [])
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(self.queue).status_code, 403)

    def test_unsuccessful_trigger_requires_scored_attempt(self):
        self.dataset.options = {'trigger': 'needs_practice'}
        self.dataset.save()
        progress = ModuleProgress.objects.get(user=self.student, enrollment=self.enrollment, module=self.source)
        progress.attempts = 1
        progress.save()
        self.assertEqual(recommendations_for(self.enrollment), [])
        self.fail_twice()
        self.assertEqual(len(recommendations_for(self.enrollment)), 1)
        progress.success = True
        progress.save()
        self.assertEqual(len(recommendations_for(self.enrollment)), 1)

    def test_ambiguous_names_require_binding_and_cross_course_binding_rejected(self):
        Module.objects.create(unit=self.unit, title='Example', provider_id='pcex')
        resolved, issues, _ = resolve_nodes(self.dataset, self.course)
        key = self.dataset.edges[0]['target']
        self.assertNotIn(key, resolved)
        self.assertEqual(issues[0]['reason'], 'Ambiguous match')
        foreign = Module.objects.create(unit=Unit.objects.create(course=Course.objects.create(id='foreign', title='Other'), title='Basics'), title='Example')
        self.client.post(self.manage, {'action': 'binding', 'revision': self.dataset.updated_at.isoformat(), 'node': key, 'module': foreign.pk})
        self.dataset.refresh_from_db()
        self.assertEqual(self.dataset.bindings, {})
        self.client.post(self.manage, {'action': 'binding', 'revision': self.dataset.updated_at.isoformat(), 'node': key, 'module': self.target.pk})
        self.dataset.refresh_from_db()
        self.assertEqual(resolve_nodes(self.dataset, self.course)[0][key].pk, self.target.pk)

    def test_cutoff_and_duplicate_targets(self):
        self.dataset.edges *= 2
        self.dataset.options = {'minimum_similarity': .9}
        self.dataset.save()
        self.fail_twice()
        self.assertEqual(recommendations_for(self.enrollment), [])
        self.dataset.options = {}
        self.dataset.save()
        self.fail_twice()
        self.assertEqual(len(recommendations_for(self.enrollment)), 1)
