from django.test import TestCase
from django.urls import reverse


class MainPageTests(TestCase):
    def test_home_page_renders(self):
        response = self.client.get(reverse('main:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Organize course sessions, study flows, embedded smart-learning content')
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
        self.assertContains(response, 'ModuLearn is a Django-based portal')

    def test_contact_page_renders(self):
        response = self.client.get(reverse('main:contact'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Questions, bugs, or deployment notes?')
