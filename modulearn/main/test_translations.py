import json
import re
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.template.loader import get_template, render_to_string
from django.test import Client, RequestFactory, TestCase
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from django.utils.translation import override

from accounts.models import User
from main.models import TranslationReport
from main.templatetags.ui_i18n import catalog
from main.i18n import translate
from main.templatetags.ui_i18n import ui_count
from main.translation_audit import build_inventory


class TranslationTests(TestCase):
    def test_source_inventory_has_no_catalog_gaps(self):
        report = build_inventory(settings.BASE_DIR, [code for code, _ in settings.LANGUAGES])
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['unmarked_template_text_for_review'], {})

    def test_parameters_remain_literal_and_serbian_counts_do_not_use_english_plural(self):
        with override('sr-latn'):
            self.assertEqual(translate('{first} {second}', first='{second}', second='literal'), '{second} literal')
            self.assertEqual(ui_count('event', 'events', 2), 'Događaji: 2')
            self.assertEqual(ui_count('unit', 'units', 21), 'Celine: 21')

    def test_english_does_not_ship_a_duplicate_browser_catalog(self):
        self.client.cookies['modulearn_language'] = 'en'
        self.assertContains(self.client.get('/'), 'id="modulearn-ui-messages" type="application/json">{}</script>')

    def test_study_participant_shell_keeps_language_and_report_controls_hidden(self):
        request = RequestFactory().get('/')
        request.user = AnonymousUser()
        with override('fr'):
            page = render_to_string('base.html', {'study_shell': True}, request=request)
        self.assertNotIn('<details class="language-menu">', page)
        self.assertNotIn('<dialog class="translation-report"', page)

    def test_all_project_templates_compile(self):
        root = Path(settings.BASE_DIR)
        for directory in [root / 'templates', *[root / app / 'templates' for app in ('accounts', 'courses', 'dashboard', 'main', 'recruitment', 'lti')]]:
            for path in directory.rglob('*.html'):
                with self.subTest(template=str(path)):
                    get_template(path.relative_to(directory).as_posix())

    def test_supported_languages_persist_and_render_without_javascript(self):
        for language, home in [('en', 'Home'), ('es', 'Inicio'), ('fr', 'Accueil'), ('sr-latn', 'Početna')]:
            with self.subTest(language=language):
                response = self.client.post(reverse('set_language'), {'language': language, 'next': '/'})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.cookies['modulearn_language'].value, language)
                response = self.client.get('/')
                self.assertContains(response, f'<html lang="{language}">')
                self.assertContains(response, home)
                self.assertContains(response, 'Srpski (latinica)')

    def test_language_switch_retains_filters_but_removes_query_language(self):
        response = self.client.get('/?lang=es&view=table&q=two+words')
        self.assertContains(response, 'value="/?view=table&amp;q=two+words"')

    def test_catalogs_have_equal_keys_and_preserve_interpolation(self):
        for language in ('fr', 'sr-latn'):
            self.assertTrue(catalog(language))
            self.assertEqual(set(catalog('es')), set(catalog(language)))
        for language in ('es', 'fr', 'sr-latn'):
            for source, translated in catalog(language).items():
                with self.subTest(language=language, source=source):
                    self.assertEqual(set(re.findall(r'\{\w+\}', source)), set(re.findall(r'\{\w+\}', translated)))
                    self.assertTrue(translated.strip())
                    if language == 'sr-latn':
                        self.assertIsNone(re.search(r'[\u0400-\u04ff]', translated))


class TranslationReportTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse('main:report_translation')
        self.payload = {'language': 'sr-latn', 'page_path': '/courses/42/?token=private#fragment',
                        'original_text': '<script>alert(1)</script>', 'suggestion': 'Ispravka'}

    def post(self, **changes):
        return self.client.post(self.url, json.dumps({**self.payload, **changes}), content_type='application/json')

    def test_anonymous_report_has_no_public_listing_and_strips_url_parameters(self):
        self.assertEqual(self.post().status_code, 201)
        report = TranslationReport.objects.get()
        self.assertEqual(report.page_path, '/courses/42/')
        self.assertIsNone(report.reporter)
        self.assertEqual(report.status, 'open')
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.client.get(reverse('admin:main_translationreport_changelist')).status_code, 302)

    def test_report_records_authenticated_reporter(self):
        user = User.objects.create_user(username='reporter')
        self.client.force_login(user)
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(TranslationReport.objects.get().reporter, user)

    def test_validation_and_rate_limit(self):
        for changes in [{'language': 'xx'}, {'original_text': ''}, {'original_text': 'x' * 1001},
                        {'suggestion': []}, {'page_path': 'https://example.org/'}, {'page_path': 'http://['}]:
            self.assertEqual(self.post(**changes).status_code, 400)
        self.assertFalse(TranslationReport.objects.exists())
        for _ in range(10): self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.post().status_code, 429)
        self.assertEqual(TranslationReport.objects.count(), 10)

    def test_csrf_is_required(self):
        response = Client(enforce_csrf_checks=True).post(self.url, json.dumps(self.payload), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_admin_can_resolve_reports_and_escapes_report_text(self):
        self.post()
        report = TranslationReport.objects.get()
        self.client.force_login(User.objects.create_superuser(username='translator-admin', password='test-only'))
        response = self.client.get(reverse('admin:main_translationreport_change', args=[report.pk]))
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.client.post(reverse('admin:main_translationreport_changelist'), {'action': 'resolve', '_selected_action': str(report.pk)})
        report.refresh_from_db()
        self.assertEqual(report.status, 'resolved')
