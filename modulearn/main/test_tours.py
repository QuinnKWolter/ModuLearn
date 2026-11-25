"""Page-guide routing plus opt-in real-browser checks against an isolated database.

PAGE_GUIDE_BROWSER=1 python manage.py test main.test_tours
"""
import os
from types import SimpleNamespace
from unittest import skipUnless

from django.contrib.auth.models import AnonymousUser
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from courses.models import Course, CourseInstance, Enrollment, Module, Unit, ModuleProgressEvent
from main.templatetags.tours import page_guide
from recruitment.services.studies import create_study_for_instructor

STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}


def fixtures():
    teacher = User.objects.create_user('guide-teacher', is_instructor=True)
    student = User.objects.create_user('guide-student', is_student=True)
    course = Course.objects.create(id='guide-test', title='Guide testing')
    course.instructors.add(teacher)
    instance = CourseInstance.objects.create(course=course, group_name='Guide session')
    instance.instructors.add(teacher)
    unit = Unit.objects.create(course=course, title='A unit', order=1)
    Module.objects.create(unit=unit, title='A practice activity', order=1)
    Enrollment.objects.create(course_instance=instance, student=student)
    study = create_study_for_instructor(teacher, title='Guide study', condition_labels='practice,similar,matched')
    return teacher, student, instance, study


class GuideSelectionTests(SimpleTestCase):
    def test_participant_and_preview_shells_never_offer_guides(self):
        request = RequestFactory().get('/')
        request.user = AnonymousUser()
        request.resolver_match = SimpleNamespace(view_name='main:home')
        for context in [{'study_shell': True}, {'participant_session': object()}]:
            self.assertIsNone(page_guide({'request': request, **context}))
        request.user = SimpleNamespace(is_anonymous_participant=True)
        self.assertIsNone(page_guide({'request': request}))

    def test_unsupported_pages_do_not_load_any_guide_assets(self):
        request = RequestFactory().get('/accounts/login/')
        request.user = AnonymousUser()
        request.resolver_match = SimpleNamespace(view_name='accounts:login')
        self.assertIsNone(page_guide({'request': request}))
        html = render_to_string('base.html', request=request)
        self.assertNotIn('page-guide.js', html)
        self.assertNotIn('data-page-guide', html)


@override_settings(STORAGES=STORAGES)
class GuidePageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher, cls.student, cls.instance, cls.study = fixtures()

    def test_guides_follow_real_views_and_use_stable_anchors(self):
        pages = [
            (None, 'main:home', [], 'home', 'home-mission'),
            (None, 'main:info', [], 'overview', 'info-learning'),
            (self.teacher, 'dashboard:instructor_dashboard', [], 'instructor', 'instructor-structures'),
            (self.student, 'dashboard:student_dashboard', [], 'student', 'student-open'),
            (self.student, 'courses:course_detail', [self.instance.pk], 'course', 'course-activity'),
            (self.teacher, 'courses:course_configuration', [self.instance.pk], 'configuration', 'config-grades'),
            (self.teacher, 'recruitment:studio', [self.study.pk], 'study', 'study-preview'),
        ]
        for user, name, args, guide, anchor in pages:
            with self.subTest(guide=guide):
                if user: self.client.force_login(user)
                else: self.client.logout()
                response = self.client.get(reverse(name, args=args))
                self.assertContains(response, f'data-guide="{guide}"')
                self.assertContains(response, f'data-tour="{anchor}"')
                self.assertNotContains(response, '<script src="/static/js/tours.generated.js"')

    def test_student_cannot_gain_configuration_access_through_a_guide(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('courses:course_configuration', args=[self.instance.pk]))
        self.assertEqual(response.status_code, 403)


@skipUnless(os.environ.get('PAGE_GUIDE_BROWSER') == '1', 'Opt-in Chrome UI checks')
@override_settings(STORAGES=STORAGES, PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class GuideBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        from playwright.sync_api import sync_playwright
        self.teacher, self.student, self.instance, self.study = fixtures()
        from django.conf import settings
        from django.test import Client
        self.logins = {}
        for user in (self.teacher, self.student):
            client = Client()
            client.force_login(user)
            cookie = client.cookies[settings.SESSION_COOKIE_NAME]
            self.logins[user.pk] = {'name': cookie.key, 'value': cookie.value, 'url': self.live_server_url}
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(channel='chrome', headless=True)
        self.context = self.browser.new_context(viewport={'width': 1365, 'height': 900}, reduced_motion='reduce')
        self.page = self.context.new_page()
        self.errors = []
        self.writes = []
        self.assets = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('request', lambda request: self.writes.append(request.url) if request.method != 'GET' else None)
        self.page.on('request', lambda request: self.assets.append(request.url) if 'tours.generated' in request.url else None)
        self.page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(self.live_server_url) else route.abort())

    def tearDown(self):
        self.context.close()
        self.browser.close()
        self.playwright.stop()
        self.assertFalse(ModuleProgressEvent.objects.exists())
        self.assertEqual(self.writes, [], 'Guides must not submit requests')
        self.assertEqual(self.errors, [], 'No uncaught browser errors')

    def login(self, user):
        self.context.add_cookies([self.logins[user.pk]])

    def visit(self, name, args=()):
        self.page.goto(self.live_server_url + reverse(name, args=args))
        self.page.locator('[data-page-guide]:visible').click()
        self.page.locator('[data-guide-start]').click()
        self.page.locator('.driver-popover').wait_for(state='visible')

    def advance(self, title):
        from playwright.sync_api import expect
        self.page.locator('.driver-popover-next-btn').click()
        expect(self.page.locator('.driver-popover-title')).to_have_text(title)

    def capture(self, name):
        if directory := os.environ.get('PAGE_GUIDE_SCREENSHOTS'):
            from pathlib import Path
            path = Path(directory)
            path.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(path / f'{name}.png'))

    def test_all_page_guides_and_read_only_modal_cleanup(self):
        from playwright.sync_api import expect
        self.page.goto(self.live_server_url)
        self.assertEqual(self.assets, [])
        self.visit('main:home')
        self.advance('Your next step'); self.advance('Explore both perspectives')
        self.page.locator('.driver-popover-next-btn').click()
        expect(self.page.locator('.driver-popover')).to_have_count(0)
        self.visit('main:info')
        self.advance('For teaching'); self.advance('For research')
        self.page.keyboard.press('Escape')
        self.login(self.teacher)
        self.visit('dashboard:instructor_dashboard')
        self.advance('Create and import')
        self.capture('instructor-courses')
        self.advance('Session controls'); self.advance('Studies')
        self.page.keyboard.press('Escape')
        self.visit('courses:course_configuration', [self.instance.pk])
        before = self.page.locator('#structureControlsForm').evaluate('(el)=>[...new FormData(el).entries()]')
        self.advance('Configuration utilities'); self.advance('Grades')
        expect(self.page.locator('#courseGradesModal')).to_be_visible()
        self.capture('configuration-grades')
        # A programmatic click, too, must not activate grade controls under a guide.
        self.page.locator('[data-grade-all="1"]').evaluate('(el)=>el.click()')
        self.advance('Save Configuration'); self.advance('Preview')
        self.page.keyboard.press('Escape')
        expect(self.page.locator('#courseGradesModal')).to_be_hidden()
        self.assertEqual(before, self.page.locator('#structureControlsForm').evaluate('(el)=>[...new FormData(el).entries()]'))
        self.visit('recruitment:studio', [self.study.pk])
        self.advance('Participant preview'); self.advance('Research Data')
        self.page.keyboard.press('Escape')
        self.login(self.student)
        self.visit('dashboard:student_dashboard')
        self.advance('Open Session'); self.page.keyboard.press('Escape')
        self.visit('courses:course_detail', [self.instance.pk])
        self.advance('Units and activities'); self.advance('Choose an activity')
        expect(self.page.locator('.course-unit').first).to_have_attribute('open', '')
        self.page.keyboard.press('Escape')
        expect(self.page.locator('.course-unit[open]')).to_have_count(0)

    def test_mobile_dark_translations_keyboard_and_resume(self):
        from playwright.sync_api import expect
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.page.emulate_media(color_scheme='dark')
        for locale, title, next_title in [('es', 'ModuLearn', 'Tu siguiente paso'),
                                         ('fr', 'ModuLearn', 'Votre prochaine étape'),
                                         ('sr-latn', 'ModuLearn', 'Vaš sledeći korak')]:
            self.context.add_cookies([{'name': 'modulearn_language', 'value': locale, 'url': self.live_server_url}])
            self.page.goto(self.live_server_url)
            self.page.evaluate('localStorage.clear()')
            self.visit('main:home')
            expect(self.page.locator('.driver-popover-title')).to_have_text(title)
            self.advance(next_title)
            for _ in range(6):
                self.page.keyboard.press('Tab')
                self.assertTrue(self.page.evaluate('!!document.activeElement.closest(".driver-popover")'))
            box = self.page.locator('.driver-popover').bounding_box()
            self.assertGreaterEqual(box['x'], 0)
            self.assertLessEqual(box['x'] + box['width'], 390)
            self.assertLessEqual(box['y'] + box['height'], 844)
            self.capture(f'mobile-{locale}')
            self.assertEqual(self.page.locator('.driver-popover').evaluate('(el)=>getComputedStyle(el).backgroundColor'), 'rgb(24, 38, 60)')
            self.page.keyboard.press('Escape')
            expect(self.page.locator('[data-page-guide]:visible')).to_be_focused()
            self.visit('main:home')
            expect(self.page.locator('.driver-popover-title')).to_have_text(next_title)
            self.page.keyboard.press('Escape')
        self.page.set_viewport_size({'width': 320, 'height': 568})
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 320)

    def test_asset_failure_retry_missing_target_and_private_storage(self):
        from playwright.sync_api import expect
        self.page.route('**/tours.generated.js', lambda route: route.abort())
        self.page.goto(self.live_server_url)
        self.page.locator('[data-page-guide]:visible').click()
        expect(self.page.locator('[data-guide-status]')).to_have_text('The guide could not be loaded. Please try again.')
        self.page.unroute('**/tours.generated.js')
        self.page.evaluate('''() => {
            Storage.prototype.setItem = () => { throw new Error('unavailable'); };
            Storage.prototype.getItem = () => { throw new Error('unavailable'); };
            document.querySelector('[data-tour="home-actions"]').remove();
        }''')
        self.page.locator('[data-guide-start]').click()
        self.advance('Your next step')
        expect(self.page.locator('.driver-popover')).to_be_visible()
        self.page.keyboard.press('Escape')
        expect(self.page.locator('.driver-popover')).to_have_count(0)

