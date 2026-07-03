from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from courses.models import Course, CourseInstance, Enrollment
from recruitment.models import ParticipantSession, RecruitmentEntryLog, RecruitmentSource


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class RecruitmentEntryFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.instructor = User.objects.create_user(username="instructor", password="pass", is_instructor=True)
        self.course = Course.objects.create(id="research101", title="Research 101")
        self.course.instructors.add(self.instructor)
        self.instance = CourseInstance.objects.create(course=self.course, group_name="wave-a")
        self.instance.instructors.add(self.instructor)

    def test_prolific_entry_provisions_participant_session(self):
        source = RecruitmentSource.objects.create(
            course_instance=self.instance,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
            prolific_study_id="bbbbbbbbbbbbbbbbbbbbbbbb",
            condition_labels="control,treatment",
        )

        response = self.client.get(reverse("recruitment:prolific_enter", args=[source.id]), {
            "PROLIFIC_PID": "5a9d64f5f6dfdd0001eaa73d",
            "STUDY_ID": "bbbbbbbbbbbbbbbbbbbbbbbb",
            "SESSION_ID": "cccccccccccccccccccccccc",
        })

        self.assertRedirects(response, reverse("courses:course_detail", args=[self.instance.id]))
        session = ParticipantSession.objects.get(recruitment_source=source)
        self.assertEqual(session.external_pid, "5a9d64f5f6dfdd0001eaa73d")
        self.assertEqual(session.external_session_id, "cccccccccccccccccccccccc")
        self.assertEqual(session.status, ParticipantSession.STATUS_IN_PROGRESS)
        self.assertTrue(session.user.is_anonymous_participant)
        self.assertTrue(session.enrollment.active)
        self.assertTrue(RecruitmentEntryLog.objects.filter(participant_session=session, accepted=True).exists())

    def test_prolific_entry_requires_valid_standard_parameters(self):
        source = RecruitmentSource.objects.create(
            course_instance=self.instance,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
        )

        response = self.client.get(reverse("recruitment:prolific_enter", args=[source.id]), {
            "PROLIFIC_PID": "not-a-prolific-id",
            "STUDY_ID": "bbbbbbbbbbbbbbbbbbbbbbbb",
            "SESSION_ID": "cccccccccccccccccccccccc",
        })

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ParticipantSession.objects.exists())
        self.assertTrue(RecruitmentEntryLog.objects.filter(accepted=False).exists())

    def test_prolific_entry_resumes_by_session_id(self):
        source = RecruitmentSource.objects.create(
            course_instance=self.instance,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
            prolific_study_id="bbbbbbbbbbbbbbbbbbbbbbbb",
        )
        params = {
            "PROLIFIC_PID": "5a9d64f5f6dfdd0001eaa73d",
            "STUDY_ID": "bbbbbbbbbbbbbbbbbbbbbbbb",
            "SESSION_ID": "cccccccccccccccccccccccc",
        }

        first_response = self.client.get(reverse("recruitment:prolific_enter", args=[source.id]), params)
        second_response = self.client.get(reverse("recruitment:prolific_enter", args=[source.id]), params)

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 302)
        self.assertEqual(ParticipantSession.objects.filter(recruitment_source=source).count(), 1)
        self.assertEqual(Enrollment.objects.filter(course_instance=self.instance).count(), 1)
        self.assertEqual(RecruitmentEntryLog.objects.filter(accepted=True).count(), 2)

    def test_sona_entry_rejects_wrong_source_platform(self):
        source = RecruitmentSource.objects.create(
            course_instance=self.instance,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
        )

        response = self.client.get(reverse("recruitment:enter", args=[source.id]), {"sona_id": "12345"})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(ParticipantSession.objects.exists())
        self.assertTrue(RecruitmentEntryLog.objects.filter(accepted=False).exists())

    def test_completed_participant_redirects_to_prolific_completion(self):
        source = RecruitmentSource.objects.create(
            course_instance=self.instance,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
            prolific_completion_code_complete="COMPLETE123",
        )
        participant = get_user_model().objects.create_user(
            username="participant_prolific",
            is_student=True,
            is_anonymous_participant=True,
        )
        participant.set_unusable_password()
        participant.save()
        enrollment = self.instance.enrollments.create(student=participant)
        session = ParticipantSession.objects.create(
            recruitment_source=source,
            user=participant,
            enrollment=enrollment,
            external_pid="pid-1",
        )
        self.client.force_login(participant)

        response = self.client.get(reverse("recruitment:complete", args=[session.uuid]))

        self.assertEqual(response.status_code, 302)
        self.assertIn("app.prolific.com/submissions/complete", response["Location"])
        session.refresh_from_db()
        self.assertEqual(session.status, ParticipantSession.STATUS_COMPLETED)
        self.assertEqual(session.completion_code_used, "COMPLETE123")

    def test_complete_current_resolves_logged_in_participant_session(self):
        source = RecruitmentSource.objects.create(
            course_instance=self.instance,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
            prolific_completion_code_complete="COMPLETE123",
        )
        participant = get_user_model().objects.create_user(
            username="participant_current",
            is_student=True,
            is_anonymous_participant=True,
        )
        enrollment = self.instance.enrollments.create(student=participant)
        session = ParticipantSession.objects.create(
            recruitment_source=source,
            user=participant,
            enrollment=enrollment,
            external_pid="pid-current",
        )
        self.client.force_login(participant)

        response = self.client.get(reverse("recruitment:complete_current", args=[self.instance.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("recruitment:complete", args=[session.uuid]))

    def test_create_source_redirects_back_to_course_configuration_when_next_is_safe(self):
        self.client.force_login(self.instructor)
        next_url = reverse("courses:course_configuration", args=[self.instance.id])

        response = self.client.post(
            reverse("recruitment:create_source", args=[self.instance.id]),
            {
                "platform": RecruitmentSource.PLATFORM_PROLIFIC,
                "label": "Pilot",
                "is_active": "on",
                "prolific_study_id": "bbbbbbbbbbbbbbbbbbbbbbbb",
                "prolific_completion_code_complete": "COMPLETE123",
                "next": next_url,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], next_url)
        self.assertTrue(RecruitmentSource.objects.filter(course_instance=self.instance, platform="prolific").exists())

    def test_anonymous_participant_profile_and_dashboard_redirect_to_assigned_course(self):
        source = RecruitmentSource.objects.create(
            course_instance=self.instance,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
        )
        self.client.get(reverse("recruitment:prolific_enter", args=[source.id]), {
            "PROLIFIC_PID": "5a9d64f5f6dfdd0001eaa73d",
            "STUDY_ID": "bbbbbbbbbbbbbbbbbbbbbbbb",
            "SESSION_ID": "cccccccccccccccccccccccc",
        })
        course_url = reverse("courses:course_detail", args=[self.instance.id])

        self.assertRedirects(self.client.get(reverse("accounts:profile")), course_url)
        self.assertRedirects(self.client.get(reverse("dashboard:student_dashboard")), course_url)

    def test_anonymous_participant_cannot_open_other_course_session(self):
        other_course = Course.objects.create(id="other-research", title="Other Research")
        other_instance = CourseInstance.objects.create(course=other_course, group_name="other-wave")
        source = RecruitmentSource.objects.create(
            course_instance=self.instance,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
        )
        self.client.get(reverse("recruitment:prolific_enter", args=[source.id]), {
            "PROLIFIC_PID": "5a9d64f5f6dfdd0001eaa73d",
            "STUDY_ID": "bbbbbbbbbbbbbbbbbbbbbbbb",
            "SESSION_ID": "cccccccccccccccccccccccc",
        })

        response = self.client.get(reverse("courses:course_detail", args=[other_instance.id]))

        self.assertEqual(response.status_code, 403)
