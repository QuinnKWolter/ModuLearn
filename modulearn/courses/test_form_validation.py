"""Required answers survive both browser and server validation failures."""
import os
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse

from accounts.models import User
from courses.models import (Course, CourseInstance, Unit, Module, Enrollment,
                            ModuleForm, ModuleFormQuestion, ModuleFormSubmission, ModuleProgress)

STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}


def setup_form(test):
    student = User.objects.create_user('form-validation-student', is_student=True)
    course = Course.objects.create(id='form-validation', title='Validation')
    instance = CourseInstance.objects.create(course=course, group_name='Validation')
    unit = Unit.objects.create(course=course, title='Forms')
    module = Module.objects.create(unit=unit, title='Required questions', module_type='form')
    Enrollment.objects.create(course_instance=instance, student=student)
    form = ModuleForm.objects.create(module=module)
    test.questions = {}
    for index, kind in enumerate(['single_choice', 'multiple_choice', 'likert', 'short_answer', 'long_answer']):
        test.questions[kind] = ModuleFormQuestion.objects.create(
            form=form, question_type=kind, prompt=kind, required=True, order=index,
            options=['First', 'Second', 'Third'] if 'choice' in kind else [])
    ModuleFormQuestion.objects.create(form=form, question_type='multiple_choice',
                                     prompt='Optional', required=False, options=['Optional'])
    test.url = reverse('courses:launch_iframe_module', args=[instance.pk, module.pk])
    test.client.force_login(student)
    test.module = module
    test.payload = {f'question_{q.pk}': value for q, value in zip(test.questions.values(),
        ['Second', ['First', 'Third'], '4', '  Keep this <text>  ', 'First line\nSecond line'])}


@override_settings(STORAGES=STORAGES)
class FormValidationTests(TestCase):
    def setUp(self):
        setup_form(self)

    def test_invalid_post_keeps_all_answers_and_does_not_record_submission(self):
        for kind, question in self.questions.items():
            with self.subTest(kind=kind):
                payload = dict(self.payload)
                payload[f'question_{question.pk}'] = [] if kind == 'multiple_choice' else '   '
                response = self.client.post(self.url, payload)
                self.assertEqual(response.status_code, 200)
                for rendered in response.context['questions']:
                    if rendered.pk == question.pk:
                        self.assertTrue(rendered.response_missing)
                    elif rendered.pk in [q.pk for q in self.questions.values()]:
                        self.assertEqual(rendered.response_value, self.payload[f'question_{rendered.pk}'])
                self.assertFalse(ModuleFormSubmission.objects.exists())
                self.assertFalse(ModuleProgress.objects.get(module=self.module).is_complete)

    def test_valid_submission_accepts_optional_empty_and_any_required_checkbox(self):
        self.payload[f'question_{self.questions["multiple_choice"].pk}'] = ['Third']
        response = self.client.post(self.url, self.payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ModuleFormSubmission.objects.count(), 1)
        self.assertTrue(ModuleProgress.objects.get(module=self.module).is_complete)

    def test_question_can_switch_between_radio_and_checkboxes_without_losing_answers(self):
        from courses.views import _update_module_form_configuration
        self.client.post(self.url, self.payload)
        question = self.questions['multiple_choice']
        saved_answer = ModuleFormSubmission.objects.get().answers.get(question=question)
        prefix = f'module_{self.module.pk}_question_{question.pk}'
        for kind, control in [('single_choice', 'radio'), ('multiple_choice', 'checkbox')]:
            with self.subTest(kind=kind):
                request = RequestFactory().post('/', {
                    f'{prefix}_question_type': kind, f'{prefix}_required': 'on',
                    f'{prefix}_options': '\n'.join(question.options),
                })
                _update_module_form_configuration(request, self.module)
                question.refresh_from_db()
                self.assertEqual(question.question_type, kind)
                self.assertEqual(question.options, ['First', 'Second', 'Third'])
                saved_answer.refresh_from_db()
                self.assertEqual(saved_answer.value, {'answer': ['First', 'Third']})
                response = self.client.get(self.url)
                self.assertContains(response, f'type="{control}" name="question_{question.pk}"')


@skipUnless(os.environ.get('FORM_VALIDATION_BROWSER') == '1', 'Opt-in Chrome integration test')
@override_settings(STORAGES=STORAGES)
class FormValidationBrowserTests(StaticLiveServerTestCase):
    def test_missing_answer_blocks_network_submit_preserves_answers_and_can_be_corrected(self):
        from playwright.sync_api import sync_playwright, expect
        setup_form(self)
        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME]
        names = {kind: f'question_{q.pk}' for kind, q in self.questions.items()}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            context = browser.new_context()
            context.add_cookies([{'name': cookie.key, 'value': cookie.value, 'url': self.live_server_url}])
            page = context.new_page()
            page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(self.live_server_url) else route.abort())
            posts = []
            page.on('request', lambda request: posts.append(request.url) if request.method == 'POST' else None)
            page.goto(self.live_server_url + self.url)
            page.wait_for_function('!!window.ModuLearnFormValidation')
            field = lambda kind: page.locator(f'[name="{names[kind]}"]')
            page.get_by_role('button', name='Submit', exact=True).click()
            expect(page.locator('.form-question-invalid')).to_have_count(5)
            expect(page.get_by_text('Select one answer.', exact=True)).to_have_count(2)
            expect(page.get_by_text('Enter an answer.', exact=True)).to_have_count(2)
            self.assertEqual(posts, [])
            field('single_choice').nth(1).check()
            field('likert').nth(3).check()
            field('short_answer').fill('Keep my answer')
            field('long_answer').fill('First line\nSecond line')
            page.get_by_role('button', name='Submit', exact=True).click()
            expect(field('multiple_choice').first.locator('xpath=ancestor::fieldset')).to_be_focused()
            expect(page.get_by_text('Select at least one answer.', exact=True)).to_be_visible()
            expect(field('multiple_choice').first).not_to_have_attribute('required', '')
            expect(page.locator('.form-question-invalid')).to_have_count(1)
            if os.environ.get('FORM_VALIDATION_SCREENSHOTS'):
                from pathlib import Path
                output = Path(os.environ['FORM_VALIDATION_SCREENSHOTS'])
                output.mkdir(parents=True, exist_ok=True)
                group = field('multiple_choice').first.locator('xpath=ancestor::fieldset')
                for theme in ['light', 'dark']:
                    page.evaluate('(dark) => document.documentElement.classList.toggle("dark", dark)', theme == 'dark')
                    group.screenshot(path=str(output / f'validation-{theme}.png'))
            expect(field('single_choice').nth(1)).to_be_checked()
            expect(field('likert').nth(3)).to_be_checked()
            expect(field('long_answer')).to_have_value('First line\nSecond line')
            self.assertEqual(posts, [])
            field('multiple_choice').nth(2).check()
            expect(page.locator('.form-question-invalid')).to_have_count(0)
            field('short_answer').fill('   ')
            page.get_by_role('button', name='Submit', exact=True).click()
            expect(field('short_answer').locator('xpath=ancestor::fieldset')).to_be_focused()
            expect(page.get_by_text('Enter an answer.', exact=True)).to_be_visible()
            self.assertEqual(posts, [])
            field('short_answer').fill('Keep my answer')
            # Also exercise the server fallback and its rendered checked/value states.
            # Native submit() bypasses JS validation, as a non-JS client would.
            field('multiple_choice').nth(2).uncheck()
            with page.expect_navigation():
                page.evaluate('HTMLFormElement.prototype.submit.call(document.querySelector("[data-study-form]"))')
            expect(field('single_choice').nth(1)).to_be_checked()
            expect(field('likert').nth(3)).to_be_checked()
            expect(field('short_answer')).to_have_value('Keep my answer')
            expect(field('long_answer')).to_have_value('First line\nSecond line')
            field('multiple_choice').nth(1).check()
            with page.expect_navigation():
                page.get_by_role('button', name='Submit', exact=True).click()
            browser.close()
        self.assertEqual(ModuleFormSubmission.objects.count(), 1)
        self.assertTrue(ModuleProgress.objects.get(module=self.module).is_complete)
