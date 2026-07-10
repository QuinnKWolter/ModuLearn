from unittest.mock import patch

from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from .backends import KnowledgeTreeBackend
from .forms import ProfileEditForm, SignUpForm
from .models import User
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

    @patch('dashboard.kt_utils.is_user_instructor_in_aggregate', return_value=False)
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

    @patch('dashboard.kt_utils.is_user_instructor_in_aggregate', return_value=True)
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
