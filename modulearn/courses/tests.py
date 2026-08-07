from unittest.mock import MagicMock, patch
import json
from urllib.parse import urlparse

from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from courses.models import (
    Course,
    CourseInstance,
    CourseProgress,
    Enrollment,
    EnrollmentCode,
    Module,
    ModuleAccessLog,
    ModuleBranchRule,
    EnrollmentModuleUnlock,
    ModuleForm,
    ModuleFormAnswer,
    ModuleFormQuestion,
    ModuleFormSubmission,
    ModuleProgress,
    ModuleProgressEvent,
    Unit,
)
from modulearn.learning.services.progress import apply_progress_snapshot
from modulearn.learning.services.access_rules import evaluate_module_access, evaluate_unit_access
from modulearn.learning.services.pcrs_tracking import capture_pcrs_result_if_possible
from modulearn.learning.selectors.courses import build_course_detail_context
from modulearn.views_proxy import (
    _cache_pcex_activity_metadata,
    _capture_pcex_activity_if_possible,
    _capture_pcex_explanation_if_possible,
    http_get_proxy_path,
)
from courses.demo_courses import create_adaptive_branching_demo_course, create_intro_python_demo_course
from courses.utils import create_course_from_json

LEGACY_SLC_URL = (
    'http://pawscomp2.sis.pitt.edu/pcex/index.html?'
    'lang=JAVA&set=artithmetic.inc_dec_operators&ch=JDecInc2'
)
MODERN_SLC_SPLICE_URL = (
    'https://acos.cs.vt.edu/html/acos-pcex/acos-pcex-examples/'
    'artithmetic_inc_dec_operators__68bdb308f6cc3d7a9cc096da?index=1'
)


class DummySession(dict):
    modified = False


class CourseProgressTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.student = User.objects.create_user(
            username='student-course',
            email='student-course@example.com',
            password='safe-pass-123',
            is_student=True,
        )
        self.instructor = User.objects.create_user(
            username='instructor-course',
            email='instructor-course@example.com',
            password='safe-pass-123',
            is_instructor=True,
            is_student=False,
        )
        self.course = Course.objects.create(id='course-1', title='Biology 101')
        self.course.instructors.add(self.instructor)
        self.instance = CourseInstance.objects.create(course=self.course, group_name='Fall 2026')
        self.instance.instructors.add(self.instructor)
        self.unit = Unit.objects.create(course=self.course, title='Unit 1')
        self.module_a = Module.objects.create(unit=self.unit, title='Module A')
        self.module_b = Module.objects.create(unit=self.unit, title='Module B')
        self.enrollment = Enrollment.objects.create(student=self.student, course_instance=self.instance)

    def test_enrollment_signal_creates_progress_rows_once(self):
        self.assertEqual(CourseProgress.objects.filter(enrollment=self.enrollment).count(), 1)
        self.assertEqual(ModuleProgress.objects.filter(enrollment=self.enrollment).count(), 2)

    def test_progress_completion_sets_completed_at_and_event(self):
        module_progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.module_a)
        apply_progress_snapshot(
          module_progress,
          source='test',
          progress=1.0,
          score=95.0,
          success=True,
        )

        module_progress.refresh_from_db()
        self.assertTrue(module_progress.is_complete)
        self.assertIsNotNone(module_progress.completed_at)
        self.assertTrue(
            ModuleProgressEvent.objects.filter(module_progress=module_progress, event_type='completion').exists()
        )

    def test_progress_completion_does_not_create_redundant_100_percent_event(self):
        module_progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.module_a)

        apply_progress_snapshot(
            module_progress,
            source='test',
            progress=1.0,
            score=100.0,
            success=True,
            event_type='progress',
        )

        event_types = list(
            ModuleProgressEvent.objects.filter(module_progress=module_progress)
            .order_by('created_at')
            .values_list('event_type', flat=True)
        )
        self.assertEqual(event_types, ['completion'])

    def test_module_session_event_records_tab_attention_event(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse('courses:record_module_session_event', args=[self.instance.id, self.module_a.id]),
            data=json.dumps({
                'event_type': 'tab_blur',
                'payload': {
                    'browser_session_id': 'session-123',
                    'client_timestamp': '2026-07-30T12:00:00.000Z',
                    'elapsed_ms': 1200,
                    'reason': 'window_blur',
                },
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertTrue(payload['tracked'])
        event = ModuleProgressEvent.objects.get(event_type='tab_blur')
        self.assertEqual(event.module, self.module_a)
        self.assertEqual(event.course_instance, self.instance)
        self.assertEqual(event.payload['browser_session_id'], 'session-123')
        self.assertEqual(event.payload['reason'], 'window_blur')

    def test_module_session_event_ignores_instructor(self):
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:record_module_session_event', args=[self.instance.id, self.module_a.id]),
            data=json.dumps({'event_type': 'tab_focus', 'payload': {'reason': 'window_focus'}}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['tracked'])
        self.assertFalse(ModuleProgressEvent.objects.filter(event_type='tab_focus').exists())

    def _pcex_worked_example_referer(self):
        return (
            'http://testserver/proxy/http/pawscomp2.sis.pitt.edu/pcex/pcex_v2/index.html?'
            f'lang=JAVA&set=artithmetic.inc_dec_operators&grp={self.instance.group_name}'
            f'&usr={self.student.username}&sid=test-session&cid={self.course.id}&module_id={self.module_a.id}'
        )

    def _cache_sample_pcex_worked_example(self, session, referer):
        request = self.factory.get(
            '/proxy/http/pawscomp2.sis.pitt.edu/pcex/pcex_v2/data/JAVA_artithmetic.inc_dec_operators.json',
            HTTP_REFERER=referer,
        )
        request.session = session
        _cache_pcex_activity_metadata(
            request,
            urlparse('http://pawscomp2.sis.pitt.edu/pcex/pcex_v2/data/JAVA_artithmetic.inc_dec_operators.json'),
            json.dumps({
                'activityName': 'artithmetic.inc_dec_operators',
                'activityGoals': [{
                    'id': 'worked-1',
                    'name': 'Increment/Decrement Operators (Case 1)',
                    'fileName': 'JDecInc1.java',
                    'fullyWorkedOut': True,
                    'lineList': [
                        {'number': 4, 'commentList': ['Define a.']},
                        {'number': 5, 'commentList': ['Define b.']},
                        {'number': 7, 'commentList': ['First output.', 'Post increment.', 'Rule note.']},
                        {'number': 9, 'commentList': ['Second output.', 'Pre increment.', 'Rule note.']},
                    ],
                }],
            }).encode('utf-8'),
        )

    def _mark_sample_pcex_activity_started(self, session, referer):
        activity_request = self.factory.post(
            '/pcex/api/track/activity',
            data=json.dumps({
                'trackingData': {
                    'user_id': self.student.username,
                    'group_id': self.instance.group_name,
                    'session_id': 'test-session',
                    'activity_set_name': 'artithmetic.inc_dec_operators',
                    'activity_type': 'ex',
                    'goal_name': 'JDecInc1.java',
                }
            }),
            content_type='application/json',
            HTTP_REFERER=referer,
        )
        activity_request.session = session
        _capture_pcex_activity_if_possible(activity_request, 'api/track/activity', HttpResponse('{}'))

    def _post_pcex_explanation(self, session, referer, line_number, explanation_level):
        explanation_request = self.factory.post(
            '/pcex/api/track/explanation',
            data=json.dumps({
                'trackingData': {
                    'tracking_id': f'{line_number}-{explanation_level}',
                    'explanation_type': 'sequential',
                    'explanation_level': explanation_level,
                    'line_number': line_number,
                }
            }),
            content_type='application/json',
            HTTP_REFERER=referer,
        )
        explanation_request.session = session
        _capture_pcex_explanation_if_possible(
            explanation_request,
            'api/track/explanation',
            HttpResponse('{}'),
        )

    def test_pcex_worked_example_explanation_clicks_update_progress(self):
        self.module_a.content_url = (
            'http://pawscomp2.sis.pitt.edu/pcex/pcex_v2/index.html?'
            'lang=JAVA&set=artithmetic.inc_dec_operators'
        )
        self.module_a.provider_id = 'pcex'
        self.module_a.save(update_fields=['content_url', 'provider_id'])
        session = DummySession()
        referer = self._pcex_worked_example_referer()
        self._cache_sample_pcex_worked_example(session, referer)
        self._mark_sample_pcex_activity_started(session, referer)

        self._post_pcex_explanation(session, referer, 5, 1)

        module_progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.module_a)
        self.assertAlmostEqual(module_progress.progress, 1 / 8)
        self.assertFalse(module_progress.is_complete)
        self.assertEqual(module_progress.state_data['completed_explanation_steps'], 1)
        self.assertEqual(module_progress.state_data['explanation_step_count'], 8)

    def test_pcex_worked_example_completes_after_all_known_explanations(self):
        self.module_a.content_url = (
            'http://pawscomp2.sis.pitt.edu/pcex/pcex_v2/index.html?'
            'lang=JAVA&set=artithmetic.inc_dec_operators'
        )
        self.module_a.provider_id = 'pcex'
        self.module_a.save(update_fields=['content_url', 'provider_id'])
        session = DummySession()
        referer = self._pcex_worked_example_referer()
        self._cache_sample_pcex_worked_example(session, referer)
        self._mark_sample_pcex_activity_started(session, referer)

        for line_number, explanation_level in [
            (4, 1), (5, 1), (7, 1), (7, 2), (7, 3), (9, 1), (9, 2), (9, 3),
        ]:
            self._post_pcex_explanation(session, referer, line_number, explanation_level)

        module_progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.module_a)
        self.assertEqual(module_progress.progress, 1.0)
        self.assertEqual(module_progress.score, 100.0)
        self.assertTrue(module_progress.is_complete)
        self.assertTrue(
            ModuleProgressEvent.objects.filter(module_progress=module_progress, event_type='completion').exists()
        )

    def test_pcex_worked_example_final_line_marks_complete_even_if_last_detail_not_emitted(self):
        self.module_a.content_url = (
            'http://pawscomp2.sis.pitt.edu/pcex/pcex_v2/index.html?'
            'lang=JAVA&set=artithmetic.inc_dec_operators'
        )
        self.module_a.provider_id = 'pcex'
        self.module_a.save(update_fields=['content_url', 'provider_id'])
        session = DummySession()
        referer = self._pcex_worked_example_referer()
        self._cache_sample_pcex_worked_example(session, referer)
        self._mark_sample_pcex_activity_started(session, referer)

        for line_number, explanation_level in [
            (4, 1), (5, 1), (7, 1), (7, 2), (7, 3), (9, 1), (9, 2),
        ]:
            self._post_pcex_explanation(session, referer, line_number, explanation_level)

        module_progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.module_a)
        self.assertEqual(module_progress.progress, 1.0)
        self.assertEqual(module_progress.score, 100.0)
        self.assertTrue(module_progress.is_complete)
        self.assertEqual(module_progress.state_data['completed_explanation_steps'], 8)
        self.assertEqual(module_progress.state_data['explanation_step_count'], 8)

    def test_pcrs_legacy_feedback_image_paths_redirect_to_local_assets(self):
        red_response = self.client.get('/mgrids/static/problems/img/red-sad-face.jpg')
        yellow_response = self.client.get('/mgrids/static/problems/img/yellow-happy-face.png')

        self.assertEqual(red_response.status_code, 200)
        self.assertEqual(red_response['Content-Type'], 'image/jpeg')
        self.assertEqual(yellow_response.status_code, 200)
        self.assertEqual(yellow_response['Content-Type'], 'image/png')

    def test_course_progress_rollup_sets_completed_at_when_all_modules_complete(self):
        for module_progress in ModuleProgress.objects.filter(enrollment=self.enrollment):
            apply_progress_snapshot(
                module_progress,
                source='test',
                progress=1.0,
                score=100.0,
                success=True,
            )

        course_progress = CourseProgress.objects.get(enrollment=self.enrollment)
        self.assertEqual(course_progress.modules_completed, 2)
        self.assertEqual(course_progress.total_modules, 2)
        self.assertEqual(course_progress.overall_progress, 100.0)
        self.assertIsNotNone(course_progress.completed_at)

    def test_invite_code_enrollment_creates_one_enrollment_and_progress_set(self):
        Enrollment.objects.filter(student=self.student, course_instance=self.instance).delete()
        CourseProgress.objects.all().delete()
        ModuleProgress.objects.all().delete()

        invitation = EnrollmentCode.objects.create(
            code='INVITE123',
            email='invited@example.com',
            course_instance=self.instance,
        )

        response = self.client.post(reverse('courses:enroll_with_code'), {
            'email': 'invited@example.com',
            'code': 'INVITE123',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Enrollment.objects.filter(course_instance=self.instance, student__email='invited@example.com').count(), 1)

        enrollment = Enrollment.objects.get(course_instance=self.instance, student__email='invited@example.com')
        self.assertEqual(CourseProgress.objects.filter(enrollment=enrollment).count(), 1)
        self.assertEqual(ModuleProgress.objects.filter(enrollment=enrollment).count(), 2)

        invitation.refresh_from_db()
        self.assertTrue(invitation.used)

    def test_invite_code_matches_existing_user_email_case_insensitively(self):
        existing_user = User.objects.create_user(
            username='quinn-existing',
            email='QuinnKWolter@Gmail.com',
            password='safe-pass-123',
        )
        invitation = EnrollmentCode.objects.create(
            code='CASE123',
            email='quinnkwolter@gmail.com',
            course_instance=self.instance,
        )

        response = self.client.post(reverse('courses:enroll_with_code'), {
            'email': 'QUINNKWOLTER@GMAIL.COM',
            'code': 'CASE123',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Enrollment.objects.filter(
                course_instance=self.instance,
                student=existing_user,
            ).exists()
        )
        self.assertEqual(
            User.objects.filter(email__iexact='quinnkwolter@gmail.com').count(),
            1,
        )
        invitation.refresh_from_db()
        self.assertTrue(invitation.used)

    def test_bulk_enrollment_reuses_user_email_case_insensitively(self):
        existing_user = User.objects.create_user(
            username='bulk-existing',
            email='Bulk.Student@Example.com',
            password='safe-pass-123',
        )
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:bulk_enroll_students', args=[self.instance.id]),
            data=json.dumps({'emails': ['BULK.STUDENT@EXAMPLE.COM']}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['success_count'], 1)
        self.assertTrue(
            Enrollment.objects.filter(
                course_instance=self.instance,
                student=existing_user,
            ).exists()
        )
        self.assertEqual(
            User.objects.filter(email__iexact='bulk.student@example.com').count(),
            1,
        )

    def test_generate_anonymous_students_creates_enrolled_login_roster(self):
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:generate_anonymous_students', args=[self.instance.id]),
            data=json.dumps({'count': 2, 'prefix': 'lab'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['success_count'], 2)
        self.assertEqual(len(payload['accounts']), 2)
        for account in payload['accounts']:
            self.assertTrue(account['username'].startswith('lab-'))
            self.assertEqual(account['email'], '')
            user = User.objects.get(username=account['username'])
            self.assertEqual(user.email, '')
            self.assertTrue(user.is_student)
            self.assertFalse(user.is_anonymous_participant)
            self.assertTrue(user.check_password(account['password']))
            self.assertTrue(
                Enrollment.objects.filter(student=user, course_instance=self.instance).exists()
            )

    def test_generate_anonymous_students_defaults_to_anon_and_username_password(self):
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:generate_anonymous_students', args=[self.instance.id]),
            data=json.dumps({'count': 1}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        account = response.json()['accounts'][0]
        self.assertTrue(account['username'].startswith('anon-'))
        self.assertEqual(account['password'], account['username'])
        user = User.objects.get(username=account['username'])
        self.assertTrue(user.check_password(account['username']))

    def test_generate_anonymous_students_can_use_random_short_passwords(self):
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:generate_anonymous_students', args=[self.instance.id]),
            data=json.dumps({'count': 1, 'password_mode': 'random'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        account = response.json()['accounts'][0]
        self.assertNotEqual(account['password'], account['username'])
        self.assertEqual(len(account['password']), 8)
        user = User.objects.get(username=account['username'])
        self.assertTrue(user.check_password(account['password']))

    @override_settings(MAX_STUDENTS_PER_SESSION=2)
    def test_generate_anonymous_students_respects_session_capacity(self):
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:generate_anonymous_students', args=[self.instance.id]),
            data=json.dumps({'count': 2}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('1 slot remain', response.json()['error'])

    @override_settings(MAX_STUDENTS_PER_SESSION=1)
    def test_bulk_enrollment_respects_session_capacity(self):
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:bulk_enroll_students', args=[self.instance.id]),
            data=json.dumps({'emails': ['new.student@example.com']}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['success_count'], 0)
        self.assertEqual(payload['error_count'], 1)
        self.assertIn('at most 1 active students', payload['error_details'][0])

    def test_generate_anonymous_students_requires_instructor(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse('courses:generate_anonymous_students', args=[self.instance.id]),
            data=json.dumps({'count': 1}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)

    @override_settings(MAX_SESSIONS_PER_COURSE=1)
    def test_create_course_instance_respects_course_session_capacity(self):
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:create_course_instance', args=[self.course.id]),
            data=json.dumps({'group_name': 'Spring 2027'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])
        self.assertIn('at most 1 active sessions', response.json()['error'])

    def test_instructor_can_delete_course_session(self):
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:delete_course_instance', args=[self.instance.id]),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertFalse(CourseInstance.objects.filter(id=self.instance.id).exists())

    def test_student_cannot_delete_course_session(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse('courses:delete_course_instance', args=[self.instance.id]),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(CourseInstance.objects.filter(id=self.instance.id).exists())

    def test_course_instructor_management_adds_existing_instructor_to_all_sessions(self):
        co_instructor = User.objects.create_user(
            username='co-instructor',
            email='Co.Teacher@Example.com',
            password='safe-pass-123',
            is_instructor=True,
            is_student=False,
        )
        other_instance = CourseInstance.objects.create(course=self.course, group_name='Spring 2027')
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:add_course_instructor', args=[self.instance.id]),
            data=json.dumps({'email': 'co.teacher@example.com'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.course.instructors.filter(id=co_instructor.id).exists())
        self.assertTrue(self.instance.instructors.filter(id=co_instructor.id).exists())
        self.assertTrue(other_instance.instructors.filter(id=co_instructor.id).exists())

        self.client.force_login(co_instructor)
        config_response = self.client.get(reverse('courses:course_configuration', args=[self.instance.id]))
        self.assertEqual(config_response.status_code, 200)

        create_response = self.client.post(
            reverse('courses:create_course_instance', args=[self.course.id]),
            data=json.dumps({'group_name': 'Summer 2027'}),
            content_type='application/json',
        )
        self.assertEqual(create_response.status_code, 200)
        new_instance = CourseInstance.objects.get(id=create_response.json()['instance_id'])
        self.assertTrue(new_instance.instructors.filter(id=self.instructor.id).exists())
        self.assertTrue(new_instance.instructors.filter(id=co_instructor.id).exists())

    def test_course_instructor_management_removes_instructor_but_keeps_last_owner(self):
        co_instructor = User.objects.create_user(
            username='co-instructor-remove',
            email='remove.teacher@example.com',
            password='safe-pass-123',
            is_instructor=True,
            is_student=False,
        )
        self.course.instructors.add(co_instructor)
        self.instance.instructors.add(co_instructor)
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:remove_course_instructor', args=[self.instance.id, co_instructor.id]),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.course.instructors.filter(id=co_instructor.id).exists())
        self.assertFalse(self.instance.instructors.filter(id=co_instructor.id).exists())

        last_owner_response = self.client.post(
            reverse('courses:remove_course_instructor', args=[self.instance.id, self.instructor.id]),
            content_type='application/json',
        )
        self.assertEqual(last_owner_response.status_code, 400)
        self.assertIn('at least one instructor', last_owner_response.json()['error'])

    def test_hidden_modules_are_not_in_student_course_context(self):
        self.module_b.is_visible = False
        self.module_b.save(update_fields=['is_visible'])

        context = build_course_detail_context(self.student, self.instance)
        visible_titles = [
            item['title']
            for card in context['unit_cards']
            for item in card['modules']
        ]

        self.assertIn('Module A', visible_titles)
        self.assertNotIn('Module B', visible_titles)

    def test_locked_module_blocks_student_launch_and_logs_denial(self):
        self.client.force_login(self.student)
        self.module_a.is_locked = True
        self.module_a.unlock_rule = {'mode': 'all', 'conditions': [{'type': 'module_completed', 'target_id': self.module_b.id}]}
        self.module_a.save(update_fields=['is_locked', 'unlock_rule'])

        response = self.client.get(reverse('courses:launch_iframe_module', args=[self.instance.id, self.module_a.id]))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ModuleAccessLog.objects.filter(
                user=self.student,
                module=self.module_a,
                course_instance=self.instance,
                event_type=ModuleAccessLog.EVENT_UNLOCK_DENIED,
            ).exists()
        )

    def test_next_accessible_module_endpoint_reflects_new_unlocks(self):
        self.client.force_login(self.student)
        self.module_b.is_locked = True
        self.module_b.unlock_rule = {'mode': 'all', 'conditions': [{'type': 'module_completed', 'target_id': self.module_a.id}]}
        self.module_b.save(update_fields=['is_locked', 'unlock_rule'])

        locked_response = self.client.get(reverse('courses:next_accessible_module', args=[self.instance.id, self.module_a.id]))
        self.assertEqual(locked_response.status_code, 200)
        self.assertFalse(locked_response.json()['available'])

        module_progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.module_a)
        apply_progress_snapshot(
            module_progress,
            source='test',
            progress=1.0,
            score=100.0,
            success=True,
        )

        unlocked_response = self.client.get(reverse('courses:next_accessible_module', args=[self.instance.id, self.module_a.id]))
        self.assertEqual(unlocked_response.status_code, 200)
        payload = unlocked_response.json()
        self.assertTrue(payload['available'])
        self.assertEqual(payload['id'], self.module_b.id)
        self.assertEqual(
            payload['url'],
            reverse('courses:launch_iframe_module', args=[self.instance.id, self.module_b.id]),
        )

    def test_pcrs_run_response_updates_module_progress(self):
        self.module_a.content_url = 'https://pcrs.utm.utoronto.ca/mgrids/problems/python/337/embed?act=PCRS&sub=py_avg_two_int_es'
        self.module_a.save(update_fields=['content_url'])
        request = RequestFactory().post(
            '/proxy/https/pcrs.utm.utoronto.ca/mgrids/problems/python/337/run',
            data='csrftoken=token&act=PCRS&sub=py_avg_two_int_es',
            content_type='application/x-www-form-urlencoded',
        )
        request.META['HTTP_REFERER'] = (
            'http://testserver/proxy/https/pcrs.utm.utoronto.ca/mgrids/problems/python/337/embed'
            f'?act=PCRS&sub=py_avg_two_int_es&grp=Fall+2026&usr={self.student.username}'
            f'&cid={self.course.id}&module_id={self.module_a.id}'
        )
        response = HttpResponse(
            json.dumps({'score': 5, 'max_score': 5, 'best': True, 'results': []}),
            content_type='application/json',
            status=200,
        )

        capture_pcrs_result_if_possible(
            request,
            'pcrs.utm.utoronto.ca',
            'mgrids/problems/python/337/run',
            response,
        )

        progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.module_a)
        self.assertEqual(progress.progress, 1.0)
        self.assertEqual(progress.score, 100.0)
        self.assertTrue(progress.is_complete)
        self.assertEqual(progress.attempts, 1)
        self.assertTrue(
            ModuleProgressEvent.objects.filter(
                module_progress=progress,
                source='pcrs',
                event_type='completion',
            ).exists()
        )

    def test_pcrs_partial_score_records_partial_progress(self):
        self.module_a.content_url = 'https://pcrs.utm.utoronto.ca/mgrids/problems/python/337/embed?act=PCRS&sub=py_avg_two_int_es'
        self.module_a.save(update_fields=['content_url'])
        request = RequestFactory().post(
            '/proxy/https/pcrs.utm.utoronto.ca/mgrids/problems/python/337/run',
            data='csrftoken=token&act=PCRS&sub=py_avg_two_int_es',
            content_type='application/x-www-form-urlencoded',
        )
        request.META['HTTP_REFERER'] = (
            'http://testserver/proxy/https/pcrs.utm.utoronto.ca/mgrids/problems/python/337/embed'
            f'?act=PCRS&sub=py_avg_two_int_es&grp=Fall+2026&usr={self.student.username}'
            f'&cid={self.course.id}&module_id={self.module_a.id}'
        )
        response = HttpResponse(
            json.dumps({'score': 3, 'max_score': 5, 'best': False, 'results': []}),
            content_type='application/json',
            status=200,
        )

        capture_pcrs_result_if_possible(
            request,
            'pcrs.utm.utoronto.ca',
            'mgrids/problems/python/337/run',
            response,
        )

        progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.module_a)
        self.assertEqual(progress.progress, 0.6)
        self.assertEqual(progress.score, 60.0)
        self.assertFalse(progress.is_complete)
        self.assertEqual(progress.attempts, 1)

    @patch('modulearn.views_proxy.requests.post')
    def test_pcrs_proxy_isolates_upstream_session_and_csrf_cookies(self, post):
        upstream_response = MagicMock()
        upstream_response.status_code = 200
        upstream_response.headers = {'Content-Type': 'application/json'}
        upstream_response.raw = None
        upstream_response.iter_content.return_value = [b'{"score": 0, "max_score": 5}']
        post.return_value.__enter__.return_value = upstream_response

        request = RequestFactory().post(
            '/proxy/https/pcrs.utm.utoronto.ca/mgrids/problems/python/337/run',
            data='csrftoken=modulearn-token&act=PCRS&sub=py_avg_two_int_es',
            content_type='application/x-www-form-urlencoded',
            HTTP_COOKIE='csrftoken=modulearn-token; sessionid=modulearn-session',
            HTTP_X_CSRFTOKEN='modulearn-token',
        )
        request.session = {
            'proxy_upstream_cookies': {
                'pcrs.utm.utoronto.ca': {
                    'csrftoken': 'pcrs-token',
                    'sessionid': 'pcrs-session',
                },
            },
        }

        response = http_get_proxy_path(
            request,
            'https/pcrs.utm.utoronto.ca/mgrids/problems/python/337/run',
        )

        self.assertEqual(response.status_code, 200)
        _, kwargs = post.call_args
        self.assertEqual(kwargs['headers']['Cookie'], 'csrftoken=pcrs-token; sessionid=pcrs-session')
        self.assertEqual(kwargs['headers']['X-CSRFToken'], 'pcrs-token')
        self.assertEqual(kwargs['data']['csrftoken'], 'pcrs-token')
        self.assertNotIn('modulearn-session', kwargs['headers']['Cookie'])

    def test_form_module_submission_marks_module_complete_and_logs_access(self):
        form_module = Module.objects.create(
            unit=self.unit,
            title='Reflection',
            module_type=Module.MODULE_TYPE_FORM,
            order=30,
        )
        module_form = ModuleForm.objects.create(module=form_module)
        question = ModuleFormQuestion.objects.create(
            form=module_form,
            prompt='How confident are you?',
            question_type=ModuleFormQuestion.TYPE_SHORT_ANSWER,
            required=True,
            order=10,
        )
        ModuleProgress.get_or_create_progress(self.student, form_module, self.instance)
        self.client.force_login(self.student)

        response = self.client.post(
            reverse('courses:launch_iframe_module', args=[self.instance.id, form_module.id]),
            {f'question_{question.id}': 'Very confident'},
        )

        self.assertEqual(response.status_code, 302)
        progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=form_module)
        self.assertTrue(progress.is_complete)
        self.assertEqual(progress.progress, 1.0)
        self.assertTrue(ModuleFormSubmission.objects.filter(form=module_form, user=self.student).exists())
        self.assertTrue(ModuleFormAnswer.objects.filter(question=question, text_value='Very confident').exists())
        self.assertTrue(
            ModuleAccessLog.objects.filter(
                user=self.student,
                module=form_module,
                event_type=ModuleAccessLog.EVENT_FORM_SUBMIT,
            ).exists()
        )

    def test_configuration_can_add_splice_module_with_splice_protocol(self):
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:course_configuration', args=[self.instance.id]),
            {
                'action': 'add_module',
                'unit_id': self.unit.id,
                'module_type': Module.MODULE_TYPE_SPLICE_SMART_CONTENT,
                'title': 'SPLICE Practice',
                'description': 'Adaptive frame content',
                'order': 40,
                'content_url': 'https://splice-learning.example/activity/1',
            },
        )

        self.assertEqual(response.status_code, 302)
        module = Module.objects.get(unit=self.unit, title='SPLICE Practice')
        self.assertEqual(module.module_type, Module.MODULE_TYPE_SPLICE_SMART_CONTENT)
        self.assertEqual(module.content_url, 'https://splice-learning.example/activity/1')
        self.assertEqual(module.supported_protocols, ['splice'])

    def test_configuration_module_type_dropdown_excludes_study_specific_form_types(self):
        self.client.force_login(self.instructor)

        response = self.client.get(reverse('courses:course_configuration', args=[self.instance.id]))

        self.assertEqual(response.status_code, 200)
        module_type_values = [value for value, _label in response.context['module_types']]
        self.assertIn(Module.MODULE_TYPE_FORM, module_type_values)
        self.assertNotIn(Module.MODULE_TYPE_STUDY_CONSENT, module_type_values)
        self.assertNotIn(Module.MODULE_TYPE_STUDY_INSTRUCTIONS, module_type_values)
        self.assertNotIn(Module.MODULE_TYPE_STUDY_PRETEST, module_type_values)
        self.assertNotIn(Module.MODULE_TYPE_STUDY_POSTTEST, module_type_values)
        self.assertNotIn(Module.MODULE_TYPE_STUDY_DEBRIEF, module_type_values)

    def test_configuration_uses_type_specific_module_editors(self):
        self.module_a.module_type = Module.MODULE_TYPE_IMPORTED
        self.module_a.content_url = 'https://smart.example.test/activity'
        self.module_a.supported_protocols = ['splice']
        self.module_a.save(update_fields=['module_type', 'content_url', 'supported_protocols'])
        self.module_b.module_type = Module.MODULE_TYPE_FILE
        self.module_b.save(update_fields=['module_type'])
        form_module = Module.objects.create(
            unit=self.unit,
            title='Reflection Form',
            module_type=Module.MODULE_TYPE_FORM,
        )
        ModuleForm.objects.create(module=form_module, instructions='Reflect briefly.')
        link_module = Module.objects.create(
            unit=self.unit,
            title='External Reading',
            module_type=Module.MODULE_TYPE_EXTERNAL_LINK,
            content_url='https://example.test/reading',
        )
        self.client.force_login(self.instructor)

        response = self.client.get(reverse('courses:course_configuration', args=[self.instance.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'name="module_{self.module_a.id}_content_url"')
        self.assertContains(response, f'name="module_{self.module_a.id}_supported_protocols"')
        self.assertNotContains(response, f'name="module_{self.module_a.id}_content_file"')
        self.assertContains(response, f'name="module_{self.module_b.id}_content_file"')
        self.assertNotContains(response, f'name="module_{self.module_b.id}_content_url"')
        self.assertContains(response, f'name="module_{form_module.id}_form_instructions"')
        self.assertNotContains(response, f'name="module_{form_module.id}_content_url"')
        self.assertNotContains(response, f'name="module_{form_module.id}_content_file"')
        self.assertContains(response, f'name="module_{link_module.id}_content_url"')
        self.assertNotContains(response, f'name="module_{link_module.id}_supported_protocols"')
        self.assertNotContains(response, f'name="module_{link_module.id}_content_file"')

    def test_configuration_page_renders_structure_explorer(self):
        self.client.force_login(self.instructor)

        response = self.client.get(reverse('courses:course_configuration', args=[self.instance.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-structure-sidebar')
        self.assertContains(response, 'data-unit-tree')
        self.assertContains(response, f'data-tree-unit data-unit-id="{self.unit.id}"')
        self.assertContains(response, f'data-tree-module data-module-id="{self.module_a.id}"')
        self.assertContains(response, f'name="module_{self.module_a.id}_unit_id"')
        self.assertContains(response, 'data-unit-empty-prompt')
        self.assertContains(response, 'Choose a unit from the structure sidebar')
        self.assertContains(response, f'data-unit-block data-unit-id="{self.unit.id}" hidden')

    def test_configuration_can_move_module_between_units(self):
        second_unit = Unit.objects.create(course=self.course, title='Unit 2', order=20)
        self.module_a.order = 10
        self.module_b.order = 20
        self.module_a.save(update_fields=['order'])
        self.module_b.save(update_fields=['order'])
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:course_configuration', args=[self.instance.id]),
            {
                'action': 'update_structure',
                f'unit_{self.unit.id}_title': self.unit.title,
                f'unit_{self.unit.id}_description': self.unit.description,
                f'unit_{self.unit.id}_order': 10,
                f'unit_{self.unit.id}_visible': '1',
                f'unit_{self.unit.id}_locked': '0',
                f'unit_{self.unit.id}_rule_type': 'none',
                f'unit_{self.unit.id}_rule_target': '',
                f'unit_{second_unit.id}_title': second_unit.title,
                f'unit_{second_unit.id}_description': second_unit.description,
                f'unit_{second_unit.id}_order': 20,
                f'unit_{second_unit.id}_visible': '1',
                f'unit_{second_unit.id}_locked': '0',
                f'unit_{second_unit.id}_rule_type': 'none',
                f'unit_{second_unit.id}_rule_target': '',
                f'module_{self.module_a.id}_title': self.module_a.title,
                f'module_{self.module_a.id}_description': self.module_a.description,
                f'module_{self.module_a.id}_unit_id': second_unit.id,
                f'module_{self.module_a.id}_order': 10,
                f'module_{self.module_a.id}_visible': '1',
                f'module_{self.module_a.id}_locked': '0',
                f'module_{self.module_a.id}_rule_type': 'none',
                f'module_{self.module_a.id}_rule_target': '',
                f'module_{self.module_b.id}_title': self.module_b.title,
                f'module_{self.module_b.id}_description': self.module_b.description,
                f'module_{self.module_b.id}_unit_id': self.unit.id,
                f'module_{self.module_b.id}_order': 10,
                f'module_{self.module_b.id}_visible': '1',
                f'module_{self.module_b.id}_locked': '0',
                f'module_{self.module_b.id}_rule_type': 'none',
                f'module_{self.module_b.id}_rule_target': '',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.module_a.refresh_from_db()
        self.module_b.refresh_from_db()
        self.assertEqual(self.module_a.unit, second_unit)
        self.assertEqual(self.module_a.order, 10)
        self.assertEqual(self.module_b.unit, self.unit)

    def test_configuration_rejects_manual_creation_of_study_specific_form_type(self):
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:course_configuration', args=[self.instance.id]),
            {
                'action': 'add_module',
                'unit_id': self.unit.id,
                'module_type': Module.MODULE_TYPE_STUDY_CONSENT,
                'title': 'Not A Manual Type',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Module.objects.filter(unit=self.unit, title='Not A Manual Type').exists())

    def test_configuration_can_edit_imported_module_source_fields(self):
        self.module_a.module_type = Module.MODULE_TYPE_IMPORTED
        self.module_a.content_url = 'https://old.example.test/activity'
        self.module_a.platform_name = 'Imported Activity'
        self.module_a.provider_id = 'old-provider'
        self.module_a.author = 'old-author'
        self.module_a.supported_protocols = ['pitt']
        self.module_a.content_data = {
            'slc_legacy_replacement': {'original_url': 'https://old.example.test/activity'},
        }
        self.module_a.save(update_fields=[
            'module_type',
            'content_url',
            'platform_name',
            'provider_id',
            'author',
            'supported_protocols',
            'content_data',
        ])
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:course_configuration', args=[self.instance.id]),
            {
                'action': 'update_structure',
                f'unit_{self.unit.id}_title': self.unit.title,
                f'unit_{self.unit.id}_description': self.unit.description,
                f'unit_{self.unit.id}_order': self.unit.order,
                f'unit_{self.unit.id}_visible': '1',
                f'unit_{self.unit.id}_locked': '0',
                f'unit_{self.unit.id}_rule_type': 'none',
                f'unit_{self.unit.id}_rule_target': '',
                f'module_{self.module_a.id}_title': self.module_a.title,
                f'module_{self.module_a.id}_description': self.module_a.description,
                f'module_{self.module_a.id}_order': self.module_a.order,
                f'module_{self.module_a.id}_visible': '1',
                f'module_{self.module_a.id}_locked': '0',
                f'module_{self.module_a.id}_rule_type': 'none',
                f'module_{self.module_a.id}_rule_target': '',
                f'module_{self.module_a.id}_content_url': 'https://new.example.test/activity',
                f'module_{self.module_a.id}_platform_name': 'Code Tracing',
                f'module_{self.module_a.id}_provider_id': 'pcex',
                f'module_{self.module_a.id}_author': 'new-author',
                f'module_{self.module_a.id}_supported_protocols': 'splice, html',
                f'module_{self.module_b.id}_title': self.module_b.title,
                f'module_{self.module_b.id}_description': self.module_b.description,
                f'module_{self.module_b.id}_order': self.module_b.order,
                f'module_{self.module_b.id}_visible': '1',
                f'module_{self.module_b.id}_locked': '0',
                f'module_{self.module_b.id}_rule_type': 'none',
                f'module_{self.module_b.id}_rule_target': '',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.module_a.refresh_from_db()
        self.assertEqual(self.module_a.content_url, 'https://new.example.test/activity')
        self.assertEqual(self.module_a.platform_name, 'Code Tracing')
        self.assertEqual(self.module_a.provider_id, 'pcex')
        self.assertEqual(self.module_a.author, 'new-author')
        self.assertEqual(self.module_a.supported_protocols, ['splice', 'html'])
        self.assertEqual(self.module_a.module_type, Module.MODULE_TYPE_IMPORTED)
        self.assertNotIn('slc_legacy_replacement', self.module_a.content_data or {})

    def test_configuration_can_toggle_course_plugins(self):
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:course_configuration', args=[self.instance.id]),
            {
                'action': 'update_plugins',
                'plugin_static_recommendations_enabled': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.course.refresh_from_db()
        self.assertTrue(self.course.plugin_config['plugins']['static_recommendations']['enabled'])
        self.assertFalse(self.course.plugin_config['plugins']['dynamic_recommendations']['enabled'])

        context = build_course_detail_context(self.student, self.instance)
        self.assertTrue(context['course_plugins']['static_recommendations'])
        self.assertFalse(context['course_plugins']['dynamic_recommendations'])

    def test_stale_masterygrids_style_flag_does_not_render_student_toggle(self):
        self.course.plugin_config = {
            'plugins': {
                'masterygrids_style': {'enabled': True},
            },
        }
        self.course.save(update_fields=['plugin_config'])

        context = build_course_detail_context(self.student, self.instance)
        self.assertNotIn('masterygrids_style', context['course_plugins'])
        self.assertFalse(context['provider_grid']['has_columns'])

        self.client.force_login(self.student)
        response = self.client.get(reverse('courses:course_detail', args=[self.instance.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-course-view-toggle="provider-grid"')
        self.assertNotContains(response, 'Provider Grid')

    def test_imported_activity_uses_resource_name_as_display_type(self):
        imported_course = create_course_from_json(
            {
                'id': 'import-resource-labels',
                'name': 'Imported Resource Labels',
                'resources': [
                    {
                        'id': 1790000000003,
                        'name': 'Programming Examples',
                        'providers': [{'id': 'pcex', 'name': 'Program Construction Examples'}],
                    },
                ],
                'units': [
                    {
                        'name': 'Variables and Operations',
                        'activities': {
                            '1790000000003': [
                                {
                                    'name': 'Increment-Decrement Operators',
                                    'url': 'http://pawscomp2.sis.pitt.edu/pcex/index.html?lang=JAVA&set=arithmetic.inc_dec',
                                    'provider_id': 'pcex',
                                    'author_id': 'r.hosseini',
                                },
                            ],
                        },
                    },
                ],
            },
            self.instructor,
        )
        imported_instance = CourseInstance.objects.create(
            course=imported_course,
            group_name='Imported Label Session',
        )
        imported_instance.instructors.add(self.instructor)
        Enrollment.objects.create(student=self.student, course_instance=imported_instance)

        module = Module.objects.get(unit__course=imported_course, title='Increment-Decrement Operators')
        self.assertEqual(module.module_type, Module.MODULE_TYPE_IMPORTED)
        self.assertEqual(module.platform_name, 'Programming Examples')
        self.assertEqual(module.display_type_label, 'Programming Examples')
        self.assertEqual(module.provider_id, 'pcex')
        self.assertEqual(module.author, 'r.hosseini')
        self.assertEqual(module.description, '')

        context = build_course_detail_context(self.student, imported_instance)
        self.assertEqual(
            context['unit_cards'][0]['modules'][0]['type_label'],
            'Programming Examples',
        )

    def test_import_replaces_legacy_slc_url_with_modern_splice_content(self):
        imported_course = create_course_from_json(
            {
                'id': 'legacy-slc-replacement',
                'name': 'Legacy SLC Replacement',
                'resources': [
                    {
                        'id': 1790000000003,
                        'name': 'Programming Examples',
                        'providers': [{'id': 'pcex', 'name': 'Program Construction Examples'}],
                    },
                ],
                'units': [
                    {
                        'name': 'Variables and Operations',
                        'activities': {
                            '1790000000003': [
                                {
                                    'name': 'Increment/Decrement Operators (Case 2)',
                                    'url': LEGACY_SLC_URL,
                                    'provider_id': 'pcex',
                                },
                            ],
                        },
                    },
                ],
            },
            self.instructor,
        )

        module = Module.objects.get(unit__course=imported_course, title='Increment/Decrement Operators (Case 2)')

        self.assertEqual(module.content_url, MODERN_SLC_SPLICE_URL)
        self.assertEqual(module.module_type, Module.MODULE_TYPE_SPLICE_SMART_CONTENT)
        self.assertEqual(module.supported_protocols[0], 'splice')
        self.assertEqual(
            module.content_data['slc_legacy_replacement']['original_url'],
            LEGACY_SLC_URL,
        )
        self.assertEqual(
            module.content_data['slc_legacy_replacement']['replacement_item_id'],
            '69cd728e7afb2475509e5e43',
        )

    def test_manual_module_creation_replaces_legacy_slc_url(self):
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:course_configuration', args=[self.instance.id]),
            {
                'action': 'add_module',
                'unit_id': self.unit.id,
                'module_type': Module.MODULE_TYPE_EXTERNAL_LINK,
                'title': 'Legacy SLC Link',
                'description': 'Old PAWS link',
                'order': 40,
                'content_url': LEGACY_SLC_URL,
            },
        )

        self.assertEqual(response.status_code, 302)
        module = Module.objects.get(unit=self.unit, title='Legacy SLC Link')
        self.assertEqual(module.content_url, MODERN_SLC_SPLICE_URL)
        self.assertEqual(module.module_type, Module.MODULE_TYPE_SPLICE_SMART_CONTENT)
        self.assertEqual(module.supported_protocols[0], 'splice')
        self.assertEqual(
            module.content_data['slc_legacy_replacement']['old_item_id'],
            '69cd72ab7afb2475509e61df',
        )

    @override_settings(
        STORAGES={
            'default': {
                'BACKEND': 'django.core.files.storage.FileSystemStorage',
            },
            'staticfiles': {
                'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
            },
        }
    )
    def test_adaptive_branching_editor_only_renders_when_plugin_enabled(self):
        self.client.force_login(self.instructor)

        response = self.client.get(reverse('courses:course_configuration', args=[self.instance.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Open Flow Mapper')
        self.assertNotContains(response, 'id="adaptiveBranchingFlowModal"')

        self.course.plugin_config = {
            'plugins': {
                'adaptive_branching': {'enabled': True, 'settings': {}},
            }
        }
        self.course.save(update_fields=['plugin_config'])

        response = self.client.get(reverse('courses:course_configuration', args=[self.instance.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Open Flow Mapper')
        self.assertContains(response, 'id="adaptiveBranchingFlowModal"')

    def test_guided_sequence_plugin_applies_default_sequential_locks(self):
        self.module_a.order = 10
        self.module_b.order = 20
        self.module_a.save(update_fields=['order'])
        self.module_b.save(update_fields=['order'])
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:course_configuration', args=[self.instance.id]),
            {
                'action': 'update_plugins',
                'plugin_guided_sequence_enabled': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.course.refresh_from_db()
        self.unit.refresh_from_db()
        self.module_a.refresh_from_db()
        self.module_b.refresh_from_db()
        self.assertTrue(self.course.plugin_config['plugins']['guided_sequence']['enabled'])
        self.assertTrue(self.unit.is_visible)
        self.assertFalse(self.unit.is_locked)
        self.assertEqual(self.unit.unlock_rule, {})
        self.assertTrue(self.module_a.is_visible)
        self.assertFalse(self.module_a.is_locked)
        self.assertEqual(self.module_a.unlock_rule, {})
        self.assertTrue(self.module_b.is_visible)
        self.assertTrue(self.module_b.is_locked)
        self.assertEqual(self.module_b.unlock_rule_type, 'module_completed')
        self.assertEqual(self.module_b.unlock_rule_target, self.module_a.id)

    @override_settings(
        STORAGES={
            'default': {
                'BACKEND': 'django.core.files.storage.FileSystemStorage',
            },
            'staticfiles': {
                'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
            },
        }
    )
    def test_module_launch_shows_next_accessible_module_button(self):
        self.module_a.module_type = Module.MODULE_TYPE_EXTERNAL_LINK
        self.module_a.content_url = 'https://example.test/module-a'
        self.module_a.order = 10
        self.module_a.save(update_fields=['module_type', 'content_url', 'order'])
        self.module_b.module_type = Module.MODULE_TYPE_EXTERNAL_LINK
        self.module_b.content_url = 'https://example.test/module-b'
        self.module_b.order = 20
        self.module_b.save(update_fields=['module_type', 'content_url', 'order'])
        self.client.force_login(self.student)

        response = self.client.get(reverse('courses:launch_iframe_module', args=[self.instance.id, self.module_a.id]))

        self.assertEqual(response.status_code, 200)
        next_url = reverse('courses:launch_iframe_module', args=[self.instance.id, self.module_b.id])
        self.assertContains(response, 'Next Module')
        self.assertContains(response, next_url)

    @override_settings(
        STORAGES={
            'default': {
                'BACKEND': 'django.core.files.storage.FileSystemStorage',
            },
            'staticfiles': {
                'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
            },
        }
    )
    def test_module_launch_disables_next_button_when_successor_is_locked(self):
        self.module_a.module_type = Module.MODULE_TYPE_EXTERNAL_LINK
        self.module_a.content_url = 'https://example.test/module-a'
        self.module_a.order = 10
        self.module_a.save(update_fields=['module_type', 'content_url', 'order'])
        self.module_b.module_type = Module.MODULE_TYPE_EXTERNAL_LINK
        self.module_b.content_url = 'https://example.test/module-b'
        self.module_b.order = 20
        self.module_b.is_locked = True
        self.module_b.unlock_rule = {'mode': 'all', 'conditions': [{'type': 'module_completed', 'target_id': 999999}]}
        self.module_b.save(update_fields=['module_type', 'content_url', 'order', 'is_locked', 'unlock_rule'])
        self.client.force_login(self.student)

        response = self.client.get(reverse('courses:launch_iframe_module', args=[self.instance.id, self.module_a.id]))

        self.assertEqual(response.status_code, 200)
        next_url = reverse('courses:launch_iframe_module', args=[self.instance.id, self.module_b.id])
        self.assertContains(response, 'No Unlocked Module')
        self.assertNotContains(response, next_url)

    @override_settings(
        STORAGES={
            'default': {
                'BACKEND': 'django.core.files.storage.FileSystemStorage',
            },
            'staticfiles': {
                'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
            },
        }
    )
    def test_codecheck_launch_preserves_direct_file_url(self):
        self.module_a.module_type = Module.MODULE_TYPE_SPLICE_SMART_CONTENT
        self.module_a.content_url = 'https://codecheck.io/files/horstmann/codecheck-python-Branches-3'
        self.module_a.provider_id = 'codecheck'
        self.module_a.supported_protocols = ['splice']
        self.module_a.save(update_fields=['module_type', 'content_url', 'provider_id', 'supported_protocols'])
        self.client.force_login(self.student)

        response = self.client.get(reverse('courses:launch_iframe_module', args=[self.instance.id, self.module_a.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'https://codecheck.io/files/horstmann/codecheck-python-Branches-3')
        self.assertNotContains(response, 'https://codecheck.io/files/wiley/')

    def test_adaptive_branching_success_unlocks_success_target_only(self):
        self.course.plugin_config = {
            'plugins': {
                'adaptive_branching': {'enabled': True, 'settings': {}},
            }
        }
        self.course.save(update_fields=['plugin_config'])
        self.module_b.is_locked = True
        self.module_b.unlock_rule = {}
        self.module_b.save(update_fields=['is_locked', 'unlock_rule'])
        module_c = Module.objects.create(unit=self.unit, title='Module C', order=30, is_locked=True)
        success_rule = ModuleBranchRule.objects.create(
            course=self.course,
            source_module=self.module_a,
            target_module=self.module_b,
            condition_type=ModuleBranchRule.CONDITION_SUCCESS,
        )
        ModuleBranchRule.objects.create(
            course=self.course,
            source_module=self.module_a,
            target_module=module_c,
            condition_type=ModuleBranchRule.CONDITION_FAILURE,
        )
        module_progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.module_a)

        apply_progress_snapshot(
            module_progress,
            source='test',
            progress=1.0,
            score=100.0,
            success=True,
            event_type='outcome',
        )

        self.assertTrue(
            EnrollmentModuleUnlock.objects.filter(
                enrollment=self.enrollment,
                module=self.module_b,
                source_rule=success_rule,
            ).exists()
        )
        self.assertFalse(
            EnrollmentModuleUnlock.objects.filter(enrollment=self.enrollment, module=module_c).exists()
        )
        unit_state = evaluate_unit_access(self.unit, self.enrollment)
        self.assertTrue(evaluate_module_access(self.module_b, self.enrollment, unit_state=unit_state).can_access)
        self.assertFalse(evaluate_module_access(module_c, self.enrollment, unit_state=unit_state).can_access)

    def test_locked_module_context_names_unlock_requirement(self):
        self.module_b.is_locked = True
        self.module_b.unlock_rule = {
            'mode': 'all',
            'conditions': [{'type': 'module_completed', 'target_id': self.module_a.id}],
        }
        self.module_b.save(update_fields=['is_locked', 'unlock_rule'])

        context = build_course_detail_context(self.student, self.instance)
        module_b = next(
            item
            for card in context['unit_cards']
            for item in card['modules']
            if item['id'] == self.module_b.id
        )

        self.assertFalse(module_b['can_access'])
        self.assertIn('Module A', module_b['lock_reason'])
        self.assertIn('completed', module_b['lock_reason'])

    def test_intro_demo_uses_sequential_unlocks(self):
        _course, instance = create_intro_python_demo_course(self.instructor)
        first_unit_modules = list(
            Module.objects.filter(unit__course=instance.course, unit__order=10).order_by('order', 'id')[:3]
        )

        self.assertEqual([module.title for module in first_unit_modules], [
            'Variable assignment',
            'Simple Printing',
            'Pythagorean hypotenuse',
        ])
        self.assertFalse(first_unit_modules[0].is_locked)
        self.assertTrue(first_unit_modules[1].is_locked)
        self.assertEqual(first_unit_modules[1].unlock_rule_type, 'module_completed')
        self.assertEqual(first_unit_modules[1].unlock_rule_target, first_unit_modules[0].id)
        self.assertTrue(first_unit_modules[1].content_url)
        self.assertEqual(first_unit_modules[1].provider_id, 'codecheck')

    def test_adaptive_demo_uses_codecheck_exercises(self):
        _course, instance = create_adaptive_branching_demo_course(self.instructor)
        modules = list(Module.objects.filter(unit__course=instance.course).order_by('order', 'id'))

        self.assertTrue(modules)
        self.assertTrue(all(module.provider_id == 'codecheck' for module in modules))
        self.assertTrue(all((module.content_url or '').startswith('https://codecheck.io/files/horstmann/') for module in modules))

    def test_adaptive_branching_failure_unlocks_failure_target_only(self):
        self.course.plugin_config = {
            'plugins': {
                'adaptive_branching': {'enabled': True, 'settings': {}},
            }
        }
        self.course.save(update_fields=['plugin_config'])
        self.module_b.is_locked = True
        self.module_b.unlock_rule = {}
        self.module_b.save(update_fields=['is_locked', 'unlock_rule'])
        module_c = Module.objects.create(unit=self.unit, title='Module C', order=30, is_locked=True)
        ModuleBranchRule.objects.create(
            course=self.course,
            source_module=self.module_a,
            target_module=self.module_b,
            condition_type=ModuleBranchRule.CONDITION_SUCCESS,
        )
        failure_rule = ModuleBranchRule.objects.create(
            course=self.course,
            source_module=self.module_a,
            target_module=module_c,
            condition_type=ModuleBranchRule.CONDITION_FAILURE,
        )
        module_progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.module_a)

        apply_progress_snapshot(
            module_progress,
            source='test',
            progress=0.5,
            score=0.0,
            success=False,
            event_type='outcome',
        )

        self.assertFalse(
            EnrollmentModuleUnlock.objects.filter(enrollment=self.enrollment, module=self.module_b).exists()
        )
        self.assertTrue(
            EnrollmentModuleUnlock.objects.filter(
                enrollment=self.enrollment,
                module=module_c,
                source_rule=failure_rule,
            ).exists()
        )

    def test_adaptive_branching_does_not_unlock_when_plugin_disabled(self):
        self.module_b.is_locked = True
        self.module_b.unlock_rule = {}
        self.module_b.save(update_fields=['is_locked', 'unlock_rule'])
        ModuleBranchRule.objects.create(
            course=self.course,
            source_module=self.module_a,
            target_module=self.module_b,
            condition_type=ModuleBranchRule.CONDITION_SUCCESS,
        )
        module_progress = ModuleProgress.objects.get(enrollment=self.enrollment, module=self.module_a)

        apply_progress_snapshot(
            module_progress,
            source='test',
            progress=1.0,
            score=100.0,
            success=True,
            event_type='outcome',
        )

        self.assertFalse(
            EnrollmentModuleUnlock.objects.filter(enrollment=self.enrollment, module=self.module_b).exists()
        )

    def test_configuration_can_add_branch_rule_and_lock_target(self):
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:course_configuration', args=[self.instance.id]),
            {
                'action': 'update_branching',
                'branch_source_module': str(self.module_a.id),
                'branch_condition_type': ModuleBranchRule.CONDITION_SUCCESS,
                'branch_target_module': str(self.module_b.id),
            },
        )

        self.assertEqual(response.status_code, 302)
        rule = ModuleBranchRule.objects.get(course=self.course)
        self.assertEqual(rule.source_module, self.module_a)
        self.assertEqual(rule.target_module, self.module_b)
        self.assertEqual(rule.condition_type, ModuleBranchRule.CONDITION_SUCCESS)
        self.module_b.refresh_from_db()
        self.assertTrue(self.module_b.is_visible)
        self.assertTrue(self.module_b.is_locked)
        self.assertEqual(self.module_b.unlock_rule, {})

    def test_configuration_renders_adaptive_branching_flow_mapper_when_enabled(self):
        self.course.plugin_config = {
            'plugins': {
                'adaptive_branching': {'enabled': True},
            },
        }
        self.course.save(update_fields=['plugin_config'])
        ModuleBranchRule.objects.create(
            course=self.course,
            source_module=self.module_a,
            target_module=self.module_b,
            condition_type=ModuleBranchRule.CONDITION_FAILURE,
        )
        self.client.force_login(self.instructor)

        response = self.client.get(reverse('courses:course_configuration', args=[self.instance.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="adaptiveBranchingFlowModal"')
        self.assertContains(response, 'data-flow-module-node')
        self.assertContains(response, 'data-flow-source-select')
        self.assertContains(response, 'data-flow-edge')

    @override_settings(
        STORAGES={
            'default': {
                'BACKEND': 'django.core.files.storage.FileSystemStorage',
            },
            'staticfiles': {
                'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
            },
        }
    )
    @patch('modulearn.core.roles.get_user_groups_with_course_ids')
    def test_configuration_page_does_not_fetch_legacy_groups(self, legacy_group_lookup):
        self.instructor.kt_login = 'KT_DEMO_INSTRUCTOR'
        self.instructor.kt_user_id = 39058
        self.instructor.save(update_fields=['kt_login', 'kt_user_id'])
        self.client.force_login(self.instructor)

        response = self.client.get(reverse('courses:course_configuration', args=[self.instance.id]))

        self.assertEqual(response.status_code, 200)
        legacy_group_lookup.assert_not_called()

    def test_configuration_unlock_rules_auto_lock_and_reject_forward_targets(self):
        self.module_a.order = 10
        self.module_b.order = 20
        self.module_a.save(update_fields=['order'])
        self.module_b.save(update_fields=['order'])
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse('courses:course_configuration', args=[self.instance.id]),
            {
                'action': 'update_structure',
                f'unit_{self.unit.id}_title': self.unit.title,
                f'unit_{self.unit.id}_description': self.unit.description,
                f'unit_{self.unit.id}_order': self.unit.order,
                f'unit_{self.unit.id}_visible': 'on',
                f'unit_{self.unit.id}_rule_type': 'none',
                f'module_{self.module_a.id}_title': self.module_a.title,
                f'module_{self.module_a.id}_description': self.module_a.description,
                f'module_{self.module_a.id}_order': self.module_a.order,
                f'module_{self.module_a.id}_visible': 'on',
                f'module_{self.module_a.id}_rule_type': 'module_completed',
                f'module_{self.module_a.id}_rule_target': str(self.module_b.id),
                f'module_{self.module_b.id}_title': self.module_b.title,
                f'module_{self.module_b.id}_description': self.module_b.description,
                f'module_{self.module_b.id}_order': self.module_b.order,
                f'module_{self.module_b.id}_visible': 'on',
                f'module_{self.module_b.id}_rule_type': 'module_completed',
                f'module_{self.module_b.id}_rule_target': str(self.module_a.id),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.module_a.refresh_from_db()
        self.module_b.refresh_from_db()
        self.assertFalse(self.module_a.is_locked)
        self.assertEqual(self.module_a.unlock_rule, {})
        self.assertTrue(self.module_b.is_locked)
        self.assertEqual(self.module_b.unlock_rule_type, 'module_completed')
        self.assertEqual(self.module_b.unlock_rule_target, self.module_a.id)

    def test_instructor_can_export_course_json(self):
        self.client.force_login(self.instructor)
        self.course.plugin_config = {
            'plugins': {
                'static_recommendations': {'enabled': True, 'settings': {}},
            }
        }
        self.course.save(update_fields=['plugin_config'])
        self.module_a.module_type = Module.MODULE_TYPE_SPLICE_SMART_CONTENT
        self.module_a.content_url = 'https://example.test/module-a'
        self.module_a.platform_name = 'JSVEE'
        self.module_a.provider_id = 'jsvee'
        self.module_a.supported_protocols = ['splice']
        self.module_a.save(update_fields=['module_type', 'content_url', 'platform_name', 'provider_id', 'supported_protocols'])

        response = self.client.get(reverse('courses:export_course', args=[self.instance.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['schema'], 'modulearn-course-export-v1')
        self.assertEqual(payload['id'], self.course.id)
        self.assertTrue(payload['plugin_config']['plugins']['static_recommendations']['enabled'])
        self.assertEqual(payload['units'][0]['activities']['JSVEE'][0]['url'], 'https://example.test/module-a')
        self.assertEqual(payload['provider_protocols']['jsvee'], ['splice'])
