from urllib.parse import parse_qs, urlsplit
import json
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, TestCase
from courses.models import Module
from modulearn.learning.services.activity_urls import normalize_activity_launch_url
from modulearn.learning.services.catalog_validation import coverage_groups, candidate_order


class CatalogValidationTests(TestCase):
    @patch('modulearn.views_proxy._infer_pcex_worked_examples_from_remote')
    def test_pcex_reported_goal_selects_metadata_when_multiple_aliases_exist(self, infer):
        from django.test import RequestFactory
        from django.contrib.sessions.backends.db import SessionStore
        from modulearn.views_proxy import _pcex_worked_example_state
        infer.return_value = {
            'title alias': {'steps': ['4:1'], 'final_explanation_line': 4},
            'Example.java': {'steps': ['4:1'], 'final_explanation_line': 4},
        }
        request = RequestFactory().post('/')
        request.session = SessionStore()
        result = _pcex_worked_example_state(request, {'example-id': ['example']},
            {'trackingData': {'goal_name': 'Example.java', 'line_number': 4, 'explanation_level': 1}})
        self.assertTrue(result[3])
        self.assertEqual(result[2], 1.0)
        self.assertEqual(result[4], 'Example.java')

    @patch('modulearn.learning.services.pcex_metadata._fetch')
    def test_current_pcex_metadata_is_cached_and_scoped_to_selected_goal(self, fetch):
        from django.core.cache import cache
        from modulearn.learning.services.pcex_metadata import catalog_goals
        cache.clear()
        fetch.return_value = json.dumps([{'activityGoals': [{'name': 'example'}, {'name': 'challenge'}]}])
        params = {'example-id': ['test__68bdb309f6cc3d7a9cc09761'], 'index': ['1']}
        self.assertEqual(catalog_goals(params), [{'name': 'challenge'}])
        params['index'] = ['0']
        self.assertEqual(catalog_goals(params), [{'name': 'example'}])
        self.assertEqual(fetch.call_count, 1)
        params['index'] = ['-1']
        self.assertIsNone(catalog_goals(params))
        self.assertIsNone(catalog_goals({'example-id': ['https://untrusted.example/data']}))

    def test_protocol_selection_recognizes_html_and_aliases(self):
        module = Module(supported_protocols=['HTML', 'LTI 1.1', 'PITT', 'SPLICE'])
        self.assertEqual(module.select_launch_protocol(), 'splice')
        self.assertEqual(module.select_launch_protocol(['LTI 1.1']), 'lti')
        module.supported_protocols = ['HTML']
        self.assertEqual(module.select_launch_protocol(), 'html')

    def test_pcex_pitt_path_preserves_activity_and_challenge(self):
        url = 'https://acos.cs.vt.edu/pitt/acos-pcex/acos-pcex-examples/test__123?index=2&module_id=9'
        result = urlsplit(normalize_activity_launch_url(url))
        self.assertEqual(result.path, '/pitt/acos-pcex/acos-pcex-examples/')
        self.assertEqual(parse_qs(result.query), {'example-id': ['test__123'], 'index': ['2'], 'module_id': ['9']})
        self.assertEqual(normalize_activity_launch_url(url.replace('acos.cs.vt.edu', 'example.com')),
                         url.replace('acos.cs.vt.edu', 'example.com'))

    def test_coverage_includes_unknown_and_deduplicates_endpoints(self):
        records = [dict(id='1', attribution={'provider': 'A'}, identity={'type': 'B'},
                        delivery=[{'protocol': 'HTML'}, {'protocol': 'html'}, {'protocol': 'PITT'}]),
                   dict(id='2', attribution={'provider': 'A'}, identity={'type': 'C'}, delivery=[])]
        groups = coverage_groups(records)
        self.assertEqual(set(groups), {('A', 'B', 'HTML'), ('A', 'B', 'PITT'), ('A', 'C', 'UNKNOWN')})
        self.assertEqual(len(groups['A', 'B', 'HTML']), 1)

    def test_broken_candidate_never_preferred_over_working(self):
        records = [dict(id='1', status='broken', identity={'title': 'Hello'}),
                   dict(id='2', status='public', identity={'title': 'Advanced task'})]
        self.assertEqual(sorted(records, key=candidate_order)[0]['id'], '2')


class CatalogCourseBuilderTests(TestCase):
    def test_isolated_course_uses_each_exact_endpoint_and_refuses_replacement(self):
        from accounts.models import User
        from courses.models import Course, CourseInstance, Enrollment
        teacher = User.objects.create_user(username='lab-teacher', is_instructor=True)
        student = User.objects.create_user(username='lab-student')
        record = {'id': 'example', 'identity': {'title': 'Hello', 'type': 'CodeConstruction'},
                  'attribution': {'provider': 'Example'}, 'delivery': [
                      {'protocol': 'HTML', 'url': 'https://example.com/html'},
                      {'protocol': 'SPLICE', 'url': 'https://example.com/splice'}]}
        def fetch(url):
            return json.dumps(record if url.endswith('/example') else [record])
        with TemporaryDirectory() as output, patch(
                'courses.management.commands.build_catalog_testing_course._fetch', side_effect=fetch):
            options = dict(output=output, create=True, course_id='isolated-lab', teacher=teacher.username,
                           student=student.username, verbosity=0)
            call_command('build_catalog_testing_course', **options)
            modules = list(Module.objects.filter(unit__course_id='isolated-lab').order_by('order'))
            self.assertEqual([m.content_url for m in modules], ['https://example.com/html', 'https://example.com/splice'])
            self.assertEqual([m.supported_protocols for m in modules], [['html'], ['splice']])
            self.assertEqual([m.order for m in modules], [0, 1])
            instance = CourseInstance.objects.get(course_id='isolated-lab')
            self.assertTrue(instance.instructors.filter(pk=teacher.pk).exists())
            self.assertEqual(Enrollment.objects.get(course_instance=instance).student, student)
            with self.assertRaises(CommandError):
                call_command('build_catalog_testing_course', **options)
            self.assertEqual(Course.objects.filter(pk='isolated-lab').count(), 1)
            self.assertEqual(Module.objects.count(), 2)
