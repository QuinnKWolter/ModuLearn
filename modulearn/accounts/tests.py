from unittest.mock import patch

from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from .backends import KnowledgeTreeBackend
from .forms import (
    KnowledgeTreePasswordResetForm, KnowledgeTreeProvisionForm,
    PasswordChangeFormCustom, ProfileEditForm, SetPasswordFormCustom, SignUpForm,
)
from .models import User
from .views import _ensure_kt_user_exists
from modulearn.core.roles import get_user_role_snapshot


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
)
class AccountPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='learner',
            email='learner@example.com',
            password='safe-pass-123',
        )

    def test_login_page_renders(self):
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)

    def test_signup_page_renders(self):
        response = self.client.get(reverse('accounts:signup'))
        self.assertEqual(response.status_code, 200)

    def test_profile_requires_authentication(self):
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 302)

    def test_profile_renders_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Profile Summary')
        self.assertContains(response, 'Student')

    def test_navbar_uses_profile_name_in_both_menus(self):
        self.user.full_name = 'Chosen Profile Name'
        self.user.first_name = '1'
        self.user.last_name = '103282274196999695239'
        self.user.save()
        self.client.force_login(self.user)

        response = self.client.get(reverse('main:home'))

        self.assertContains(response, 'Chosen Profile Name', count=2)
        self.assertNotContains(response, '103282274196999695239')

    def test_navbar_falls_back_to_username_for_numeric_imported_names(self):
        self.user.full_name = '1**103282274196999695239**'
        self.user.first_name = '1'
        self.user.last_name = '103282274196999695239'
        self.user.save()
        self.client.force_login(self.user)

        response = self.client.get(reverse('main:home'))

        self.assertContains(response, '>learner</span>', count=2)
        self.assertNotContains(response, '103282274196999695239')

    def test_display_name_retains_human_names_and_does_not_change_stored_fields(self):
        for full_name, first_name, last_name, expected in [
            ('  Quinn Wolter  ', 'Old', 'Name', 'Quinn Wolter'),
            ('', 'María', 'García', 'María García'),
            (None, '李', '明', '李 明'),
            ('', '', '', 'learner'),
        ]:
            with self.subTest(expected=expected):
                self.user.full_name = full_name
                self.user.first_name = first_name
                self.user.last_name = last_name
                self.assertEqual(self.user.get_display_name(), expected)
                self.assertEqual(self.user.full_name, full_name)

    def test_instructor_navbar_wins_over_student_enrollment_and_kt_groups(self):
        from courses.models import Course, CourseInstance, Enrollment

        self.user.is_instructor = True
        self.user.kt_login = 'remote-instructor'
        self.user.kt_groups = []
        self.user.save()
        course = Course.objects.create(id='nav-test-course', title='Navbar Test')
        instance = CourseInstance.objects.create(course=course, group_name='Navbar Test')
        Enrollment.objects.create(student=self.user, course_instance=instance)
        self.client.force_login(self.user)

        with patch('modulearn.core.roles.get_user_groups_with_course_ids') as remote_lookup:
            response = self.client.get(reverse('main:home'))

        keys = {item['key'] for item in response.context['primary_navigation']}
        self.assertIn('instructor', keys)
        self.assertIn('analytics', keys)
        self.assertNotIn('student', keys)
        self.assertContains(response, f'href="{reverse("dashboard:instructor_dashboard")}"')
        self.assertNotContains(response, f'href="{reverse("dashboard:student_dashboard")}"')
        remote_lookup.assert_not_called()

    def test_existing_session_sees_admin_role_change_on_next_request(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('main:home'))
        self.assertTrue(response.context['effective_is_student'])

        User.objects.filter(pk=self.user.pk).update(is_instructor=True, is_student=False)
        response = self.client.get(reverse('main:home'))

        self.assertTrue(response.context['effective_is_instructor'])
        self.assertFalse(response.context['effective_is_student'])
        self.assertRedirects(
            self.client.get(reverse('dashboard:student_dashboard')),
            reverse('dashboard:instructor_dashboard'), fetch_redirect_response=False,
        )

    @override_settings(KNOWLEDGETREE={'AUTH_ENABLED': False})
    def test_normal_password_login_renders_instructor_navigation(self):
        self.user.is_instructor = True
        self.user.save(update_fields=['is_instructor'])

        response = self.client.post(reverse('accounts:login'), {
            'username': self.user.username, 'password': 'safe-pass-123',
        }, follow=True)

        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)
        keys = {item['key'] for item in response.context['primary_navigation']}
        self.assertIn('instructor', keys)
        self.assertNotIn('student', keys)

    def test_instructor_flag_overrides_stale_participant_state(self):
        from courses.models import Course, CourseInstance, Enrollment
        from recruitment.models import ParticipantSession, RecruitmentSource

        self.user.is_instructor = True
        self.user.is_anonymous_participant = True
        self.user.save()
        course = Course.objects.create(id='stale-participant', title='Stale Participant')
        instance = CourseInstance.objects.create(course=course, group_name='Stale Participant')
        enrollment = Enrollment.objects.create(student=self.user, course_instance=instance)
        source = RecruitmentSource.objects.create(course_instance=instance, platform='prolific')
        ParticipantSession.objects.create(
            recruitment_source=source, user=self.user, enrollment=enrollment,
            external_pid='test-instructor', status='in_progress',
        )
        self.client.force_login(self.user)

        for route in ('main:home', 'accounts:profile', 'dashboard:instructor_dashboard'):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                keys = {item['key'] for item in response.context['primary_navigation']}
                self.assertIn('instructor', keys)
                self.assertNotIn('student', keys)
                self.assertContains(response, f'href="{reverse("accounts:profile")}"')

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_instructor)
        self.assertTrue(self.user.is_anonymous_participant)

    def test_role_snapshot_recomputes_after_explicit_role_change(self):
        self.assertFalse(get_user_role_snapshot(self.user)['effective_is_instructor'])
        self.user.is_instructor = True
        self.user.save(update_fields=['is_instructor'])

        snapshot = get_user_role_snapshot(self.user)

        self.assertTrue(snapshot['effective_is_instructor'])
        self.assertFalse(snapshot['effective_is_student'])

    def test_profile_edit_preserves_concurrent_instructor_promotion(self):
        form = ProfileEditForm(instance=self.user, data={'email': '', 'full_name': 'Updated Name'})
        self.assertTrue(form.is_valid(), form.errors)
        User.objects.filter(pk=self.user.pk).update(is_instructor=True, is_student=False)

        form.save()

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_instructor)
        self.assertFalse(self.user.is_student)
        self.assertEqual(self.user.full_name, 'Updated Name')

    def test_password_forms_preserve_concurrent_instructor_promotion(self):
        for form_class in (
            PasswordChangeFormCustom, SetPasswordFormCustom,
            KnowledgeTreePasswordResetForm, KnowledgeTreeProvisionForm,
        ):
            with self.subTest(form=form_class.__name__):
                user = User.objects.create_user(username=form_class.__name__, password='old-safe-pass-123')
                form = form_class(user=user, data={
                    'old_password': 'old-safe-pass-123',
                    'new_password1': 'new-safe-pass-456', 'new_password2': 'new-safe-pass-456',
                })
                self.assertTrue(form.is_valid(), form.errors)
                User.objects.filter(pk=user.pk).update(is_instructor=True, is_student=False)

                form.save()

                user.refresh_from_db()
                self.assertTrue(user.is_instructor)
                self.assertFalse(user.is_student)
                self.assertTrue(user.check_password('new-safe-pass-456'))

    @patch('courses.utils.logger')
    @patch('courses.utils.requests.post')
    def test_course_authoring_credentials_preserve_concurrent_role_change(self, post, _logger):
        from courses.utils import get_course_auth_token, reset_course_authoring_password

        post.return_value.text = 'synthetic-token'
        post.return_value.json.return_value = {}
        for action in (get_course_auth_token, reset_course_authoring_password):
            with self.subTest(action=action.__name__):
                user = User.objects.create_user(username=action.__name__)
                User.objects.filter(pk=user.pk).update(is_instructor=True, is_student=False)

                action(user)

                user.refresh_from_db()
                self.assertTrue(user.is_instructor)
                self.assertFalse(user.is_student)
                self.assertTrue(user.course_authoring_password)

    def test_user_emails_are_normalized_on_save(self):
        user = User.objects.create_user(
            username='mixed-email',
            email='  QuinnKWolter@Gmail.COM ',
            password='safe-pass-123',
        )

        self.assertEqual(user.email, 'quinnkwolter@gmail.com')

    def test_signup_rejects_case_insensitive_duplicate_email(self):
        form = SignUpForm(data={
            'username': 'another-learner',
            'email': 'LEARNER@EXAMPLE.COM',
            'full_name': 'Another Learner',
            'password1': 'safe-pass-456',
            'password2': 'safe-pass-456',
            'role': 'student',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_student_signup_allows_blank_email(self):
        form = SignUpForm(data={
            'username': 'no-email-learner',
            'email': '',
            'full_name': 'No Email Learner',
            'password1': 'safe-pass-456',
            'password2': 'safe-pass-456',
            'role': 'student',
        })

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save(commit=False)
        user.full_name = form.cleaned_data['full_name']
        user.is_student = True
        user.save()
        self.assertEqual(user.email, '')

    def test_profile_rejects_case_insensitive_duplicate_email(self):
        other = User.objects.create_user(
            username='other-learner',
            email='other@example.com',
            password='safe-pass-123',
        )

        form = ProfileEditForm(
            instance=other,
            data={'email': 'LEARNER@EXAMPLE.COM', 'full_name': 'Other Learner'},
        )

        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_profile_allows_blank_email(self):
        form = ProfileEditForm(
            instance=self.user,
            data={'email': '', 'full_name': 'Learner Without Email'},
        )

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.email, '')
        self.assertEqual(user.full_name, 'Learner Without Email')

    def test_database_rejects_case_insensitive_duplicate_email(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(
                username='duplicate-learner',
                email='LEARNER@EXAMPLE.COM',
                password='safe-pass-123',
            )

    def test_email_shaped_username_authenticates_case_insensitively(self):
        user = User.objects.create_user(
            username='QuinnKWolter@Gmail.com',
            email='QuinnKWolter@Gmail.com',
            password='safe-pass-123',
        )

        authenticated = authenticate(
            username='quinnkwolter@gmail.COM',
            password='safe-pass-123',
        )

        self.assertEqual(authenticated.pk, user.pk)


class KnowledgeTreeBackendRoleTests(TestCase):
    def setUp(self):
        self.backend = KnowledgeTreeBackend()

    @override_settings(KNOWLEDGETREE={'AUTH_ENABLED': True}, PAWS_DATABASE={'HOST': 'test.invalid'})
    @patch('accounts.knowledgetree_auth.KnowledgeTreeAuthService')
    def test_kt_provisioning_does_not_overwrite_role_corrected_during_lookup(self, service):
        user = User.objects.create_user(username='provisioning-user', is_student=True)

        def remote_lookup(_username):
            User.objects.filter(pk=user.pk).update(is_instructor=True, is_student=False)
            return {'user_id': 5001, 'login': user.username}

        service.return_value.check_user_exists_in_database.side_effect = remote_lookup
        _ensure_kt_user_exists(user, 'test-only-password')

        user.refresh_from_db()
        self.assertTrue(user.is_instructor)
        self.assertFalse(user.is_student)
        self.assertEqual(user.kt_user_id, 5001)

    @patch('dashboard.kt_utils.lookup_user_instructor_status_in_aggregate')
    def test_kt_metadata_save_does_not_overwrite_concurrent_role_change(self, lookup):
        user = User.objects.create_user(username='concurrent-user', kt_login='concurrent-user')
        update_metadata = self.backend._update_user_from_kt

        def concurrent_update(stale_user, data):
            User.objects.filter(pk=user.pk).update(is_instructor=True, is_student=False)
            return update_metadata(stale_user, data)

        with patch.object(self.backend, '_update_user_from_kt', side_effect=concurrent_update):
            result = self.backend._get_or_create_user({'login': user.kt_login, 'name': 'Remote Name'})

        user.refresh_from_db()
        self.assertTrue(user.is_instructor)
        self.assertFalse(user.is_student)
        self.assertTrue(result.is_instructor)
        self.assertEqual(user.full_name, 'Remote Name')
        lookup.assert_not_called()

    def test_metadata_only_save_does_not_overwrite_newer_student_role(self):
        user = User.objects.create_user(username='stale-instructor', is_instructor=True)
        User.objects.filter(pk=user.pk).update(is_instructor=False, is_student=True)
        user.kt_login = 'linked-instructor'

        user.save(update_fields=['kt_login'])

        user.refresh_from_db()
        self.assertFalse(user.is_instructor)
        self.assertTrue(user.is_student)

    def test_explicit_instructor_save_still_clears_student_flag(self):
        user = User.objects.create_user(username='promoted-student')
        user.is_instructor = True
        user.save(update_fields=['is_instructor'])
        user.refresh_from_db()
        self.assertTrue(user.is_instructor)
        self.assertFalse(user.is_student)

    @override_settings(
        KNOWLEDGETREE={'AUTH_ENABLED': True},
        STORAGES={
            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
        },
    )
    @patch('accounts.backends.KnowledgeTreeAuthService')
    @patch('dashboard.kt_utils.lookup_user_instructor_status_in_aggregate', return_value=False)
    def test_password_login_kt_fallback_preserves_instructor_for_each_identity_match(self, lookup, service):
        for match in ('id', 'login', 'email', 'username'):
            with self.subTest(match=match):
                user = User.objects.create_user(
                    username='instructor-' + match, password='local-password',
                    email=match + '@example.invalid', is_instructor=True,
                    kt_user_id=6001 if match == 'id' else None,
                    kt_login='remote-' + match if match == 'login' else None,
                )
                service.return_value.authenticate.return_value = {
                    'user_id': 6001 if match == 'id' else None,
                    'login': user.username if match == 'username' else 'remote-' + match,
                    'email': user.email if match == 'email' else '',
                    'name': 'Remote Instructor', 'groups': [],
                }
                response = self.client.post(reverse('accounts:login'), {
                    'username': user.username, 'password': 'remote-password',
                })
                self.assertEqual(response.status_code, 302)
                self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
                user.refresh_from_db()
                self.assertTrue(user.is_instructor)
                self.assertFalse(user.is_student)
                home = self.client.get(reverse('main:home'))
                keys = {item['key'] for item in home.context['primary_navigation']}
                self.assertIn('instructor', keys)
                self.assertNotIn('student', keys)
                self.client.logout()
        lookup.assert_not_called()

    @patch('dashboard.kt_utils.lookup_user_instructor_status_in_aggregate', return_value=False)
    def test_existing_instructor_is_not_demoted_by_unconfirmed_aggregate_lookup(self, _lookup):
        user = User.objects.create_user(
            username='kt-instructor',
            password='safe-pass-123',
            kt_user_id=1001,
            kt_login='kt-instructor',
            is_instructor=True,
            is_student=False,
        )

        authenticated_user = self.backend._get_or_create_user({
            'user_id': 1001,
            'login': 'kt-instructor',
            'name': 'KT Instructor',
            'email': 'kt-instructor@example.com',
            'groups': [],
        })

        user.refresh_from_db()
        self.assertEqual(authenticated_user.pk, user.pk)
        self.assertTrue(user.is_instructor)
        self.assertFalse(user.is_student)

    @patch('dashboard.kt_utils.lookup_user_instructor_status_in_aggregate', return_value=True)
    def test_confirmed_aggregate_instructor_does_not_promote_existing_student(self, _lookup):
        user = User.objects.create_user(
            username='kt-student',
            password='safe-pass-123',
            kt_user_id=1002,
            kt_login='kt-student',
            is_instructor=False,
            is_student=True,
        )

        self.backend._get_or_create_user({
            'user_id': 1002,
            'login': 'kt-student',
            'name': 'KT Student',
            'email': 'kt-student@example.com',
            'groups': [],
        })

        user.refresh_from_db()
        self.assertFalse(user.is_instructor)
        self.assertTrue(user.is_student)

    def test_kt_identity_does_not_make_student_effective_instructor(self):
        user = User.objects.create_user(
            username='RITEL_DEMO_Student',
            password='safe-pass-123',
            kt_user_id=39059,
            kt_login='RITEL_DEMO_Student',
            kt_groups=['RITELDemoGroup'],
            is_instructor=False,
            is_student=True,
        )

        snapshot = get_user_role_snapshot(user, include_legacy_groups=True)

        self.assertFalse(snapshot['effective_is_instructor'])
        self.assertTrue(snapshot['effective_is_student'])
        self.assertEqual(snapshot['primary_role'], 'student')
        self.assertEqual(snapshot['legacy_course_groups'], [])

    @patch('dashboard.kt_utils.lookup_user_instructor_status_in_aggregate', return_value=None)
    def test_new_kt_user_gets_no_role_when_aggregate_lookup_is_unavailable(self, _lookup):
        user = self.backend._get_or_create_user({
            'user_id': 1003,
            'login': 'kt-unknown-role',
            'name': 'KT Unknown Role',
            'email': 'kt-unknown-role@example.com',
            'groups': [],
        })

        self.assertIsNotNone(user)
        self.assertFalse(user.is_instructor)
        self.assertFalse(user.is_student)
