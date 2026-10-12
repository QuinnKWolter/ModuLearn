from django.test import TestCase
from django.urls import reverse


class MainPageTests(TestCase):
    def test_legacy_audience_urls_use_account_role_without_tabs(self):
        for audience in ['students', 'teachers', 'researchers']:
            response = self.client.get(reverse('main:home_' + audience))
            self.assertEqual(response.context['home_audience'], 'overview')
            self.assertNotContains(response, 'home-audiences')
            self.assertTrue(next(item for item in response.context['primary_navigation'] if item['key'] == 'home')['is_active'])

    def test_authenticated_default_and_research_view_do_not_change_roles(self):
        from accounts.models import User
        for role, audience in [('is_student', 'students'), ('is_instructor', 'teachers')]:
            user = User.objects.create_user(username=audience, **{role: True})
            self.client.force_login(user)
            session = self.client.session
            session['home_audience'] = 'researchers'
            session.save()
            self.assertEqual(self.client.get(reverse('main:home')).context['home_audience'], audience)
            response = self.client.get(reverse('main:home_researchers'))
            self.assertEqual(response.context['home_audience'], audience)
            self.assertContains(response, reverse('dashboard:instructor_dashboard' if role == 'is_instructor' else 'dashboard:student_dashboard'))
            user.refresh_from_db()
            self.assertTrue(getattr(user, role))
            self.client.logout()

    def test_home_page_renders(self):
        response = self.client.get(reverse('main:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Free and open-source tools')
        self.assertContains(response, 'name="language" value="es"')
        self.assertContains(response, 'src="/static/js/i18n.js"')

    def test_language_toggle_sets_spanish_cookie_and_html_language(self):
        response = self.client.post(reverse('set_language'), {
            'language': 'es',
            'next': reverse('main:home'),
        })
        self.assertEqual(response.status_code, 302)

        response = self.client.get(reverse('main:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html lang="es">')
        self.assertContains(response, 'Herramientas libres y de código abierto')
        self.assertContains(response, 'language-toggle-option is-active')

    def test_lang_query_parameter_sets_active_language_and_cookie(self):
        response = self.client.get(reverse('main:about') + '?lang=es')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html lang="es">')
        self.assertEqual(response.cookies['modulearn_language'].value, 'es')

        response = self.client.get(reverse('main:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html lang="es">')

    def test_about_page_renders(self):
        response = self.client.get(reverse('main:about'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Open educational technology.')
        self.assertContains(response, 'For learning')

    def test_contact_page_renders(self):
        response = self.client.get(reverse('main:contact'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Something not working?')

    def test_spanish_info_is_translated_before_javascript(self):
        response = self.client.get(reverse('main:info') + '?lang=es')
        self.assertContains(response, 'Tecnología educativa abierta.')
        self.assertContains(response, 'Para enseñar')

    def test_feature_catalogs_preserve_named_placeholders(self):
        import re
        from main.templatetags.ui_i18n import catalog
        for source, translated in catalog('es').items():
            self.assertEqual(set(re.findall(r'\{\w+\}', source)), set(re.findall(r'\{\w+\}', translated)), source)

    def test_ui_placeholders_are_escaped_and_content_is_not_translated(self):
        from django.template import Context, Template
        from django.utils.translation import override
        with override('es'):
            rendered = Template('{% load ui_i18n %}{% ui "Adding to: {unit}" unit=title %}').render(Context({'title': '<b>Home</b>'}))
        self.assertEqual(rendered, 'Añadir a: &lt;b&gt;Home&lt;/b&gt;')
