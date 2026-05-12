from django.test import TestCase
from django.urls import reverse


class MainPageTests(TestCase):
    def test_home_page_renders(self):
        response = self.client.get(reverse('main:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Modular learning flows without a sprawling interface.')

    def test_about_page_renders(self):
        response = self.client.get(reverse('main:about'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'About ModuLearn')

    def test_contact_page_renders(self):
        response = self.client.get(reverse('main:contact'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Contact the maintainer')
