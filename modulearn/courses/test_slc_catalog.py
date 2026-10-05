import copy
import json
import ssl
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from courses.models import Course, CourseInstance, Enrollment, Module, ModuleProgress, Unit
from modulearn.learning.services import slc_catalog as catalog

PITT = {
    'id': 'abc123', 'status': 'public', 'listed_at': '2026-09-01',
    'identity': {'title': 'Loops and arrays', 'type': 'CodeCompletionProblem'},
    'attribution': {'provider': 'PCEX', 'authors': [{'name': 'Author'}]},
    'languages': {'programming_languages': ['Java'], 'content_language': 'en'},
    'content': {'prompt': '<p>Complete the loop.</p>', 'source_code': 'while (true) {}'},
    'classification': {'knowledge_components': {'ontology': {'concepts': ['iteration']}}},
    'delivery': [
        {'protocol': 'PITT', 'url': 'https://example.org/pitt'},
        {'protocol': 'HTML', 'url': 'https://example.org/html'},
        {'protocol': 'SPLICE', 'url': 'https://example.org/splice?index=2'},
        {'protocol': 'LTI 1.1', 'url': 'https://example.org/lti'},
    ],
    'links': {'demo_url': 'https://example.org/demo'}, 'rights': {'license': 'MIT'}, 'tags': ['loop;color=blue'],
}
SPLICE = {
    'id': 42, 'title': 'Python functions', 'platform_name': 'CodeCheck', 'author': ['Second author'],
    'programming_language': ['Python'], 'natural_language': ['en'], 'description': 'Functions',
    'protocol': ['LTI 1.1', 'SPLICE'], 'protocol_url': ['https://example.org/lti', 'https://example.org/splice2'],
    'iframe_url': 'https://example.org/demo2', 'license': 'MIT',
}
TEST_SETTINGS = {
    'CACHES': {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    'STORAGES': {'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}},
}


@override_settings(**TEST_SETTINGS)
class CatalogAdapterTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_pitt_tls_keeps_hostname_and_trusted_root_verification(self):
        context = catalog._tls_context(catalog.PITT_API)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertFalse(context.verify_flags & ssl.VERIFY_X509_PARTIAL_CHAIN)

    @patch.object(catalog.cache, 'set', side_effect=OSError('cache unavailable'))
    @patch.object(catalog, '_fetch', return_value=json.dumps([PITT]))
    def test_cache_write_failure_does_not_discard_live_catalog(self, fetch, cache_set):
        items, warnings = catalog.catalog_items('pitt')
        self.assertEqual(len(items), 1)
        self.assertEqual(warnings, [])

    @patch.object(catalog.cache, 'get', side_effect=OSError('cache unavailable'))
    @patch.object(catalog, '_fetch', return_value=json.dumps([PITT]))
    def test_cache_read_failure_still_fetches_live_catalog(self, fetch, cache_get):
        items, warnings = catalog.catalog_items('pitt')
        self.assertEqual(len(items), 1)
        self.assertEqual(warnings, [])

    def test_splice_preferred_regardless_of_endpoint_order(self):
        for raw, source in ((PITT, 'pitt'), (SPLICE, 'splice')):
            item = catalog.normalize_item(source, raw, detail=True)
            self.assertEqual(item['selected_delivery']['protocol'], 'SPLICE')
            self.assertEqual(item['metadata'], raw)
            self.assertEqual(catalog.module_catalog_fields(item)['supported_protocols'], ['splice'])

    def test_missing_url_is_not_invented_and_demo_is_separate(self):
        raw = copy.deepcopy(PITT)
        raw['delivery'] = [{'protocol': 'SPLICE'}, {'protocol': 'PITT', 'url': 'https://example.org/pitt'}]
        item = catalog.normalize_item('pitt', raw, detail=True)
        self.assertEqual(item['selected_delivery']['protocol'], 'PITT')
        self.assertEqual(item['demo_url'], 'https://example.org/demo')
        raw['delivery'] = [{'protocol': 'SPLICE'}]
        self.assertIsNone(catalog.normalize_item('pitt', raw, detail=True)['selected_delivery'])

    def test_unsafe_links_and_broken_items_cannot_be_imported(self):
        raw = copy.deepcopy(PITT)
        raw['links']['demo_url'] = 'javascript:alert(1)'
        raw['delivery'] = [{'protocol': 'SPLICE', 'url': 'javascript:alert(1)'}]
        item = catalog.normalize_item('pitt', raw, detail=True)
        self.assertEqual(item['demo_url'], '')
        with self.assertRaises(ValueError):
            catalog.module_catalog_fields(item)
        raw = {**PITT, 'status': 'broken:pending-fix'}
        with self.assertRaises(ValueError):
            catalog.module_catalog_fields(catalog.normalize_item('pitt', raw, detail=True))

    @patch.object(catalog, '_fetch')
    def test_catalog_adapters_parse_actual_upstream_shapes(self, fetch):
        fetch.side_effect = [json.dumps([PITT]), '<script>window.allItems = ' + json.dumps([SPLICE]) + ';</script>']
        items, warnings = catalog.catalog_items()
        self.assertEqual(len(items), 2)
        self.assertEqual(warnings, [])
        self.assertEqual(items[0]['concepts'], ['iteration'])
        self.assertEqual(items[0]['tags'], ['loop'])
        self.assertEqual(items[0]['description'], 'Complete the loop.')
        catalog.catalog_items()
        self.assertEqual(fetch.call_count, 2)

    @patch.object(catalog, '_fetch')
    def test_outage_uses_stale_cache_and_keeps_other_source_available(self, fetch):
        cache.set('slc-catalog:v1:pitt:list', {'at': 0, 'data': [PITT]})
        fetch.side_effect = OSError('offline')
        items, warnings = catalog.catalog_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(len(warnings), 2)
        self.assertIn('cached', warnings[0])

    @patch.object(catalog, '_fetch')
    def test_bad_item_identifiers_never_become_upstream_requests(self, fetch):
        for source, item_id in [('pitt', '../auth'), ('http://localhost', '1'), ('pitt', 'x?url=http://localhost')]:
            with self.assertRaises(ValueError):
                catalog.catalog_item(source, item_id)
        fetch.assert_not_called()


@override_settings(**TEST_SETTINGS)
class CatalogWorkflowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(username='catalog-teacher', is_instructor=True)
        self.student = User.objects.create_user(username='catalog-student', is_student=True)
        self.course = Course.objects.create(id='catalog-course', title='Catalog course')
        self.course.instructors.add(self.teacher)
        self.instance = CourseInstance.objects.create(course=self.course, group_name='Catalog session')
        self.instance.instructors.add(self.teacher)
        self.unit = Unit.objects.create(course=self.course, title='Unit')
        self.enrollment = Enrollment.objects.create(student=self.student, course_instance=self.instance)
        self.search = reverse('courses:catalog_search', args=[self.instance.pk])
        self.detail = reverse('courses:catalog_detail', args=[self.instance.pk])
        self.configure = reverse('courses:course_configuration', args=[self.instance.pk])
        self.client.force_login(self.teacher)
        cache.set('slc-catalog:v1:pitt:list', {'at': catalog.time.time(), 'data': [PITT]})
        cache.set('slc-catalog:v1:splice:list', {'at': catalog.time.time(), 'data': [SPLICE]})
        cache.set('slc-catalog:v1:pitt:item:abc123', {'at': catalog.time.time(), 'data': PITT})

    def payload(self):
        return {'action': 'add_module', 'unit_id': self.unit.pk, 'module_type': 'splice_smart_content',
                'title': 'My loop activity', 'description': 'Instructor description',
                'catalog_source': 'pitt', 'catalog_item_id': 'abc123',
                'content_url': 'https://untrusted.invalid/override'}

    def test_search_filter_facets_and_detail(self):
        response = self.client.get(self.search, {'q': 'iteration', 'languages': 'Java', 'protocols': 'SPLICE'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total'], 1)
        self.assertEqual(response.json()['items'][0]['source'], 'pitt')
        self.assertNotIn('metadata', response.json()['items'][0])
        detail = self.client.get(self.detail, {'source': 'pitt', 'id': 'abc123'}).json()
        self.assertEqual(detail['metadata']['content']['source_code'], 'while (true) {}')
        self.assertEqual(detail['selected_delivery']['protocol'], 'SPLICE')

    def test_catalog_import_resolves_server_metadata_and_syncs_student_progress(self):
        response = self.client.post(self.configure, self.payload())
        self.assertRedirects(response, self.configure)
        module = Module.objects.get(unit=self.unit)
        self.assertEqual(module.title, 'My loop activity')
        self.assertEqual(module.description, 'Instructor description')
        self.assertEqual(module.content_url, 'https://example.org/splice?index=2')
        self.assertEqual(module.supported_protocols, ['splice'])
        self.assertEqual(module.provider_id, 'pcex_ch')
        self.assertEqual(module.author, 'Author')
        self.assertEqual(module.content_data['catalog']['metadata'], PITT)
        self.assertTrue(ModuleProgress.objects.filter(module=module, enrollment=self.enrollment).exists())

    def test_import_cannot_target_another_course_unit(self):
        other = Course.objects.create(id='other', title='Other')
        unit = Unit.objects.create(course=other, title='Other unit')
        self.client.post(self.configure, {**self.payload(), 'unit_id': unit.pk})
        self.assertFalse(Module.objects.exists())

    def test_browsing_and_preview_metadata_do_not_create_modules(self):
        self.client.get(self.search)
        self.client.get(self.detail, {'source': 'pitt', 'id': 'abc123'})
        self.assertFalse(Module.objects.exists())

    def test_students_and_unassigned_instructors_cannot_browse_or_import(self):
        outsider = User.objects.create_user(username='other-teacher', is_instructor=True)
        for user in (self.student, outsider):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.search).status_code, 403)
            self.assertEqual(self.client.get(self.detail).status_code, 403)
            self.assertEqual(self.client.post(self.configure, self.payload()).status_code, 403)
        self.assertFalse(Module.objects.exists())

    def test_pagination_and_empty_results(self):
        rows = [{**PITT, 'id': str(i), 'identity': {**PITT['identity'], 'title': f'Activity {i:02}'}} for i in range(30)]
        cache.set('slc-catalog:v1:pitt:list', {'at': catalog.time.time(), 'data': rows})
        data = self.client.get(self.search, {'source': 'pitt', 'page': 2}).json()
        self.assertEqual(data['total'], 30)
        self.assertEqual(len(data['items']), 6)
        self.assertEqual(self.client.get(self.search, {'q': 'no such title'}).json()['total'], 0)

    def test_facet_counts_replace_own_choice_and_apply_every_other_filter(self):
        python = copy.deepcopy(PITT)
        python['id'] = 'python'
        python['languages']['programming_languages'] = ['Python', 'Python']
        cache.set('slc-catalog:v1:pitt:list', {'at': catalog.time.time(), 'data': [PITT, python]})
        data = self.client.get(self.search, {'provider': 'PCEX', 'languages': 'Java', 'source': 'pitt'}).json()
        counts = {field: {option['value']: option['count'] for option in options}
                  for field, options in data['facets'].items()}
        self.assertEqual(data['total'], 1)
        # Python replaces Java; it is not intersected with the selected language.
        self.assertEqual(counts['languages'], {'Java': 1, 'Python': 1})
        self.assertEqual(data['facet_totals']['languages'], 2)
        # Provider counts must see the language filter, even though the provider
        # dropdown appears earlier in the UI / backend field iteration.
        self.assertEqual(counts['provider'], {'CodeCheck': 0, 'PCEX': 1})
        self.assertEqual(counts['source'], {'pitt': 1, 'splice': 0})

    def test_zero_count_choices_remain_and_repopulate_after_filters_clear(self):
        filtered = self.client.get(self.search, {'q': 'iteration'}).json()
        options = {option['value']: option['count'] for option in filtered['facets']['languages']}
        self.assertEqual(options, {'Java': 1, 'Python': 0})
        cleared = self.client.get(self.search).json()
        self.assertEqual({o['value']: o['count'] for o in cleared['facets']['languages']}, {'Java': 1, 'Python': 1})
        empty = self.client.get(self.search, {'q': 'no such title', 'provider': 'Removed provider'}).json()
        self.assertEqual(empty['total'], 0)
        self.assertIn({'value': 'Removed provider', 'label': 'Removed provider', 'count': 0}, empty['facets']['provider'])
        self.assertTrue(all(o['count'] == 0 for options in empty['facets'].values() for o in options))

    def test_configuration_has_unit_entry_point_and_catalog_picker(self):
        response = self.client.get(self.configure)
        self.assertContains(response, 'data-unit-add-module')
        self.assertContains(response, 'data-open-slc-catalog')
        self.assertContains(response, 'id="slcCatalog"')
