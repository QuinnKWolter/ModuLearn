from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from courses.models import Course, CourseInstance
from recruitment.models import ParticipantSession, RecruitmentEntryLog, RecruitmentSource


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
            prolific_study_id="study-1",
            condition_labels="control,treatment",
        )

        response = self.client.get(reverse("recruitment:enter", args=[source.id]), {
            "PROLIFIC_PID": "5a9d64f5f6dfdd0001eaa73d",
            "STUDY_ID": "study-1",
            "SESSION_ID": "session-1",
        })

        self.assertEqual(response.status_code, 302)
        session = ParticipantSession.objects.get(recruitment_source=source)
        self.assertEqual(session.external_pid, "5a9d64f5f6dfdd0001eaa73d")
        self.assertTrue(session.user.is_anonymous_participant)
        self.assertTrue(session.enrollment.active)
        self.assertTrue(RecruitmentEntryLog.objects.filter(participant_session=session, accepted=True).exists())

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
