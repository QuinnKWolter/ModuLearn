"""Workspace permissions/parity and opt-in real-browser navigation checks."""
import json
import os
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from courses.models import Course, CourseInstance, ModuleProgressEvent
from main.test_tours import STORAGES, fixtures
from modulearn.learning.selectors.dashboard import build_instructor_dashboard_context


@override_settings(STORAGES=STORAGES)
class WorkspaceTests(TestCase):
    def setUp(self):
        self.teacher, self.student, self.instance, self.study = fixtures()
        self.client.force_login(self.teacher)

    def test_session_only_instructor_sees_session_without_structure_permissions(self):
        course = Course.objects.create(id='assigned-only', title='Assigned course')
        session = CourseInstance.objects.create(course=course, group_name='Assigned session')
        session.instructors.add(self.teacher)
        context = build_instructor_dashboard_context(self.teacher)
        assigned = next(item for item in context['courses'] if item.pk == course.pk)
        self.assertFalse(assigned.dashboard_can_manage_structure)
        self.assertEqual([item.pk for item in assigned.dashboard_sessions], [session.pk])
        page = self.client.get(reverse('dashboard:instructor_dashboard'))
        self.assertContains(page, f'id="workspace-session-{session.pk}"')
        self.assertNotContains(page, 'class="btn btn-outline-danger delete-course-btn" data-course-id="assigned-only"')

    def test_actions_remain_available_and_unique(self):
        from html.parser import HTMLParser
        class IDs(HTMLParser):
            def __init__(self): super().__init__(); self.ids = []
            def handle_starttag(self, tag, attrs):
                if value := dict(attrs).get('id'): self.ids.append(value)
        response = self.client.get(reverse('dashboard:instructor_dashboard'))
        for text in ['Import From Authoring', 'Import JSON', 'Create New Study', 'New Session',
                     'Delete Structure', 'LTI Setup', 'Enrollment', 'Analytics', 'Activity',
                     'Delete Session', 'Configure Activities', 'Study Setup', 'Prolific Settings',
                     'Export Study', 'Delete Study', 'Clear Participants &amp; Progress']:
            self.assertContains(response, text)
        parser = IDs(); parser.feed(response.content.decode())
        self.assertEqual(len(parser.ids), len(set(parser.ids)), 'Each action/form must have one DOM instance')
        self.assertNotContains(response, 'id="courseStructuresModal"')
        self.assertNotContains(response, 'id="studiesModal"')

    def test_other_users_sessions_are_not_in_the_workspace(self):
        CourseInstance.objects.create(course=self.instance.course, group_name='Private other section')
        response = self.client.get(reverse('dashboard:instructor_dashboard'))
        self.assertNotContains(response, 'Private other section')

    def test_empty_workspace_keeps_creation_and_import_available(self):
        empty = User.objects.create_user('new-teacher', is_instructor=True)
        self.client.force_login(empty)
        response = self.client.get(reverse('dashboard:instructor_dashboard'))
        self.assertContains(response, 'id="workspace-welcome"')
        self.assertContains(response, 'Create New Study')
        self.assertContains(response, 'id="importCourseButton"')
        self.assertNotContains(response, 'data-workspace-default')


@skipUnless(os.environ.get('PAGE_GUIDE_BROWSER') == '1', 'Opt-in Chrome UI checks')
@override_settings(STORAGES=STORAGES, PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class WorkspaceBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        from playwright.sync_api import sync_playwright
        self.teacher, self.student, self.instance, self.study = fixtures()
        self.client.force_login(self.teacher)
        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME]
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(channel='chrome', headless=True)
        self.context = self.browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
        self.context.add_cookies([{'name': cookie.key, 'value': cookie.value, 'url': self.live_server_url}])
        self.page = self.context.new_page()
        self.errors = []; self.writes = []; self.legacy_calls = 0; self.legacy_mode = 'success'
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('request', lambda request: self.writes.append(request.url) if request.method != 'GET' else None)
        self.legacy_url = reverse('dashboard:get_legacy_groups_api')
        self.page.route('**/*', self.route)

    def route(self, route):
        request = route.request
        if self.legacy_url in request.url:
            self.legacy_calls += 1
            groups = [{'group_name': 'Legacy Java', 'group_login': 'old-java', 'course_ids': ['12']},
                      {'group_name': '<img src=x onerror=alert(1)>', 'group_login': 'safe<&>', 'course_ids': []}]
            if self.legacy_mode == 'empty': groups = []
            route.fulfill(status=503 if self.legacy_mode == 'failure' else 200, content_type='application/json',
                          body=json.dumps({'success': self.legacy_mode != 'failure', 'groups': groups}))
        elif '/resources/' in request.url:
            route.fulfill(content_type='application/json', body=json.dumps({'success': True, 'resources': []}))
        elif request.url.startswith(self.live_server_url): route.continue_()
        else: route.abort()

    def tearDown(self):
        self.context.close(); self.browser.close(); self.playwright.stop()
        self.assertEqual(self.errors, [])
        self.assertEqual(self.writes, [], 'Navigating/managing dialog visibility must not mutate data')
        self.assertFalse(ModuleProgressEvent.objects.exists())

    def visit(self):
        self.page.goto(self.live_server_url + reverse('dashboard:instructor_dashboard'))
        self.page.locator('.workspace-ready').wait_for()

    def capture(self, name):
        if folder := os.environ.get('PAGE_GUIDE_SCREENSHOTS'):
            path = Path(folder); path.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(path / f'workspace-{name}.png'))

    def test_session_actions_dialog_focus_and_course_selection(self):
        from playwright.sync_api import expect
        self.visit()
        panel = self.page.locator(f'#workspace-session-{self.instance.pk}')
        expect(panel).to_be_visible()
        self.capture('session')
        for name in ['Configure', 'View Course', 'Enrollment', 'Analytics', 'Activity', 'LTI Setup', 'Delete Session']:
            expect(panel.get_by_label(name, exact=True)).to_be_visible()
        panel.get_by_label('Enrollment', exact=True).click()
        expect(self.page.locator('#manageEnrollmentModal')).to_be_visible()
        expect(self.page.locator('#currentCourseInstanceId')).to_have_value(str(self.instance.pk))
        self.page.keyboard.press('Shift+Tab')
        self.assertTrue(self.page.evaluate('!!document.activeElement.closest("#manageEnrollmentModal")'))
        self.page.keyboard.press('Escape')
        expect(self.page.locator('#manageEnrollmentModal')).to_be_hidden()
        expect(panel.get_by_label('Enrollment', exact=True)).to_be_focused()
        panel.locator('[data-workspace-jump]').click()
        visible = self.page.locator('[data-workspace-panel]:visible')
        visible.get_by_role('button', name='New Session', exact=True).click()
        expect(self.page.locator('#newSessionModal')).to_be_visible()
        expect(self.page.locator('#courseId')).to_have_value(self.instance.course_id)
        self.page.keyboard.press('Escape')
        visible.get_by_role('link', name='Guide session', exact=False).click()
        expect(panel).to_be_visible()

    def test_study_preserves_edits_search_history_and_restore(self):
        from playwright.sync_api import expect
        self.visit()
        study_link = self.page.locator(f'[data-workspace-select][aria-controls="workspace-study-{self.study.pk}"]')
        study_link.click()
        panel = self.page.locator(f'#workspace-study-{self.study.pk}')
        panel.get_by_role('button', name='Prolific Settings', exact=True).click()
        panel.locator('input[name="max_participants"]').fill('15')
        self.capture('study')
        self.page.locator('[data-workspace-default]').first.click()
        study_link.click()
        expect(panel.locator('input[name="max_participants"]')).to_have_value('15')
        self.page.locator('#workspaceSearch').fill('Guide study')
        expect(self.page.locator('[data-workspace-default]').first).to_be_hidden()
        self.page.reload()
        expect(panel).to_be_visible()
        expect(self.page.locator('#workspaceSearch')).to_have_value('Guide study')
        self.page.locator('[data-workspace-clear]').click()
        self.page.locator('[data-workspace-default]').first.click()
        self.page.go_back()
        expect(panel).to_be_visible()
        self.page.get_by_role('button', name='Create New Study', exact=True).click()
        expect(self.page.locator('#createStudyModal')).to_be_visible()
        expect(self.page.locator('#createStudyModal input[name="study_template_json"]')).to_be_visible()
        self.page.keyboard.press('Escape')

    def test_legacy_loading_retry_safe_names_and_no_extra_fetch_on_selection(self):
        from playwright.sync_api import expect
        self.legacy_mode = 'failure'; self.visit()
        expect(self.page.locator('#legacyGroupsRetry')).to_be_visible()
        self.legacy_mode = 'success'; self.page.locator('#legacyGroupsRetry').click()
        self.page.locator('[data-workspace-legacy-nav]').get_by_role('link', name='Legacy Java').click()
        panel = self.page.locator('[data-workspace-panel]:visible')
        expect(panel.get_by_role('heading', name='Legacy Java')).to_be_visible()
        expect(panel.get_by_role('button', name='View Resources')).to_be_visible()
        expect(self.page.locator('[data-workspace-legacy-nav] img')).to_have_count(0)
        expect(panel.get_by_role('link', name='View Dashboard')).to_have_attribute('href', __import__('re').compile('.*old-java.*'))
        self.capture('legacy')
        self.page.locator('[data-workspace-default]').first.click()
        self.page.locator('[data-workspace-legacy-nav]').get_by_role('link', name='Legacy Java').click()
        self.assertEqual(self.legacy_calls, 2)
        self.page.reload()
        expect(self.page.locator('[data-workspace-panel]:visible').get_by_role('heading', name='Legacy Java')).to_be_visible()

    def test_mobile_keyboard_empty_legacy_and_no_results(self):
        from playwright.sync_api import expect
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.page.emulate_media(color_scheme='dark')
        self.legacy_mode = 'empty'; self.visit()
        expect(self.page.locator('#workspaceSidebar')).to_be_hidden()
        self.page.locator('[data-workspace-browse]').click()
        expect(self.page.locator('#workspaceSearch')).to_be_focused()
        expect(self.page.locator('#legacyGroupsSection')).to_be_hidden()
        self.page.locator('#workspaceSearch').fill('not found')
        expect(self.page.locator('[data-workspace-no-results]')).to_be_visible()
        self.page.locator('[data-workspace-clear]').click()
        self.page.locator('[data-workspace-select]').first.focus()
        self.page.keyboard.press('End'); self.page.keyboard.press('Enter')
        expect(self.page.locator(f'#workspace-study-{self.study.pk}')).to_be_visible()
        expect(self.page.locator('#workspaceSidebar')).to_be_hidden()
        expect(self.page.locator(f'#workspaceStudyTitle{self.study.pk}')).to_be_focused()
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 390)
        self.capture('mobile-study')

    def test_translated_toolbar_and_small_screen_layout(self):
        from playwright.sync_api import expect
        self.page.set_viewport_size({'width': 320, 'height': 740})
        for locale, label in [('es', 'Explorar cursos y estudios'), ('fr', 'Parcourir les cours et les études'), ('sr-latn', 'Pregledaj kurseve i studije')]:
            self.context.add_cookies([{'name': 'modulearn_language', 'value': locale, 'url': self.live_server_url}])
            self.visit()
            expect(self.page.locator('[data-workspace-browse]')).to_have_text(label)
            expect(self.page.locator('[data-workspace-panel]:visible h2')).to_have_text('Guide session')
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 320)
            self.page.locator('[data-workspace-browse]').click()
            expect(self.page.locator('#workspaceSidebar')).to_be_visible()
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 320)
