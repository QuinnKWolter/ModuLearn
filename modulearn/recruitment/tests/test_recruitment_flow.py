from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from courses.models import (
    Course,
    CourseInstance,
    Enrollment,
    EnrollmentModuleUnlock,
    Module,
    ModuleBranchRule,
    ModuleFormSubmission,
    ModuleProgress,
    ModuleProgressEvent,
    Unit,
)
from modulearn.learning.services.progress import apply_progress_snapshot
from recruitment.models import ParticipantSession, RecruitmentEntryLog, RecruitmentSource, Study, StudyCondition
from recruitment.services.studies import create_study_for_instructor


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

    def make_study(self, title="Research Study"):
        study = Study.objects.create(
            title=title,
            course_instance=self.instance,
            status=Study.STATUS_ACTIVE,
        )
        study.instructors.add(self.instructor)
        StudyCondition.objects.create(study=study, label="control", name="Control", order=10)
        StudyCondition.objects.create(study=study, label="treatment", name="Treatment", order=20)
        return study

    def test_prolific_entry_provisions_participant_session(self):
        study = self.make_study()
        source = RecruitmentSource.objects.create(
            study=study,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
            prolific_study_id="bbbbbbbbbbbbbbbbbbbbbbbb",
        )

        response = self.client.get(reverse("recruitment:study_launch", args=[study.slug]), {
            "PROLIFIC_PID": "5a9d64f5f6dfdd0001eaa73d",
            "STUDY_ID": "bbbbbbbbbbbbbbbbbbbbbbbb",
            "SESSION_ID": "cccccccccccccccccccccccc",
        })

        self.assertRedirects(response, reverse("recruitment:sessions"))
        session = ParticipantSession.objects.get(recruitment_source=source)
        self.assertEqual(session.external_pid, "5a9d64f5f6dfdd0001eaa73d")
        self.assertEqual(session.external_session_id, "cccccccccccccccccccccccc")
        self.assertEqual(session.status, ParticipantSession.STATUS_IN_PROGRESS)
        self.assertTrue(session.user.is_anonymous_participant)
        self.assertTrue(session.enrollment.active)
        self.assertEqual(session.enrollment.course_instance, self.instance)
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

    def test_prolific_entry_accepts_synthetic_participant_ids_for_testing(self):
        study = self.make_study(title="Synthetic PID Study")
        source = RecruitmentSource.objects.create(
            study=study,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
            prolific_study_id="bbbbbbbbbbbbbbbbbbbbbbbb",
        )

        response = self.client.get(reverse("recruitment:study_launch", args=[study.slug]), {
            "PROLIFIC_PID": "test-participant-01",
            "STUDY_ID": "bbbbbbbbbbbbbbbbbbbbbbbb",
            "SESSION_ID": "testsession01",
        })

        self.assertRedirects(response, reverse("recruitment:sessions"))
        session = ParticipantSession.objects.get(recruitment_source=source)
        self.assertEqual(session.external_pid, "test-participant-01")
        self.assertEqual(session.external_session_id, "testsession01")

    def test_prolific_study_launch_accepts_short_session_identifier(self):
        study = self.make_study(title="RITEL Demo Study")
        source = RecruitmentSource.objects.create(
            study=study,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
            prolific_study_id="6a584b56ace9629c9093ace6",
        )

        response = self.client.get(reverse("recruitment:study_launch", args=[study.slug]), {
            "PROLIFIC_PID": "6a3951b4b326f99b82331661",
            "STUDY_ID": "6a584b56ace9629c9093ace6",
            "SESSION_ID": "0jfggbb63i5q",
        })

        self.assertRedirects(response, reverse("recruitment:sessions"))
        session = ParticipantSession.objects.get(recruitment_source=source)
        self.assertEqual(session.external_session_id, "0jfggbb63i5q")
        self.assertEqual(session.external_study_id, "6a584b56ace9629c9093ace6")

    def test_prolific_study_launch_backfills_source_study_id(self):
        study = self.make_study(title="Auto Captured Study")
        source = RecruitmentSource.objects.create(
            study=study,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
        )

        response = self.client.get(reverse("recruitment:study_launch", args=[study.slug]), {
            "PROLIFIC_PID": "6a3951b4b326f99b82331661",
            "STUDY_ID": "6a584b56ace9629c9093ace6",
            "SESSION_ID": "0jfggbb63i5q",
        })

        self.assertRedirects(response, reverse("recruitment:sessions"))
        source.refresh_from_db()
        self.assertEqual(source.prolific_study_id, "6a584b56ace9629c9093ace6")

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

    def test_prolific_entry_resumes_by_participant_id_if_session_id_changes(self):
        source = RecruitmentSource.objects.create(
            course_instance=self.instance,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
            prolific_study_id="bbbbbbbbbbbbbbbbbbbbbbbb",
            condition_strategy=RecruitmentSource.CONDITION_BALANCED,
            condition_labels="control,treatment",
        )
        base_params = {
            "PROLIFIC_PID": "5a9d64f5f6dfdd0001eaa73d",
            "STUDY_ID": "bbbbbbbbbbbbbbbbbbbbbbbb",
            "SESSION_ID": "cccccccccccccccccccccccc",
        }

        self.client.get(reverse("recruitment:prolific_enter", args=[source.id]), base_params)
        second_params = {**base_params, "SESSION_ID": "dddddddddddddddddddddddd"}
        self.client.get(reverse("recruitment:prolific_enter", args=[source.id]), second_params)

        self.assertEqual(ParticipantSession.objects.filter(recruitment_source=source).count(), 1)
        session = ParticipantSession.objects.get(recruitment_source=source)
        self.assertEqual(session.external_session_id, "dddddddddddddddddddddddd")
        self.assertEqual(session.condition, "control")

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

    def test_create_study_source_redirects_to_safe_next_url(self):
        self.client.force_login(self.instructor)
        study = self.make_study()
        next_url = reverse("dashboard:instructor_dashboard")

        response = self.client.post(
            reverse("recruitment:create_study_source", args=[study.id]),
            {
                "platform": RecruitmentSource.PLATFORM_PROLIFIC,
                "label": "Pilot",
                "is_active": "on",
                "prolific_study_id": "bbbbbbbbbbbbbbbbbbbbbbbb",
                "prolific_completion_code_complete": "COMPLETE123",
                "condition_labels": "control,treatment",
                "next": next_url,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], next_url)
        self.assertTrue(RecruitmentSource.objects.filter(study=study, platform="prolific").exists())

    def test_create_study_source_uses_study_conditions(self):
        self.client.force_login(self.instructor)
        study = self.make_study()

        self.client.post(
            reverse("recruitment:create_study_source", args=[study.id]),
            {
                "platform": RecruitmentSource.PLATFORM_PROLIFIC,
                "label": "Control wave",
                "is_active": "on",
                "condition_labels": "control,treatment",
            },
        )

        source = RecruitmentSource.objects.get(study=study, platform="prolific")
        self.assertEqual(source.condition_labels, "")
        self.assertEqual(source.conditions, ["control", "treatment"])
        self.assertEqual(source.session_condition, "control")

    def test_create_source_rejects_sona_while_disabled(self):
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse("recruitment:create_source", args=[self.instance.id]),
            {
                "platform": RecruitmentSource.PLATFORM_SONA,
                "label": "SONA pilot",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(RecruitmentSource.objects.filter(course_instance=self.instance).exists())

    def test_course_configuration_no_longer_renders_prolific_url_template(self):
        self.client.force_login(self.instructor)
        source = RecruitmentSource.objects.create(
            course_instance=self.instance,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
            label="Pilot",
        )

        response = self.client.get(reverse("courses:course_configuration", args=[self.instance.id]))

        self.assertEqual(response.status_code, 200)
        expected_path = reverse("recruitment:prolific_enter", args=[source.id])
        self.assertNotContains(response, expected_path)
        self.assertNotContains(response, "PROLIFIC_PID={{%PROLIFIC_PID%}}")

    def test_instructor_dashboard_renders_study_prolific_url_template(self):
        self.client.force_login(self.instructor)
        study = self.make_study()
        RecruitmentSource.objects.create(
            study=study,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
            label="Pilot",
        )

        response = self.client.get(reverse("dashboard:instructor_dashboard"))

        self.assertEqual(response.status_code, 200)
        expected_path = reverse("recruitment:study_launch", args=[study.slug])
        self.assertContains(response, expected_path)
        self.assertContains(response, "PROLIFIC_PID={{%PROLIFIC_PID%}}")
        self.assertContains(response, "STUDY_ID={{%STUDY_ID%}}")
        self.assertContains(response, "SESSION_ID={{%SESSION_ID%}}")

    def test_created_study_has_immediate_copyable_prolific_url(self):
        self.client.force_login(self.instructor)

        response = self.client.post(
            reverse("recruitment:create_study"),
            {
                "title": "Immediate Prolific URL Study",
                "version_label": "v1.0",
                "condition_labels": "control,treatment",
                "description": "Check URL readiness.",
            },
        )

        self.assertEqual(response.status_code, 302)
        study = Study.objects.get(title="Immediate Prolific URL Study")
        source = RecruitmentSource.objects.get(study=study, platform=RecruitmentSource.PLATFORM_PROLIFIC)
        self.assertTrue(source.is_active)
        self.assertEqual(source.condition_strategy, RecruitmentSource.CONDITION_BALANCED)

        dashboard_response = self.client.get(reverse("dashboard:instructor_dashboard"))
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertContains(dashboard_response, reverse("recruitment:study_launch", args=[study.slug]))
        self.assertContains(dashboard_response, "PROLIFIC_PID={{%PROLIFIC_PID%}}")

    def test_created_study_uses_before_main_post_units(self):
        study = create_study_for_instructor(
            self.instructor,
            title="Structured Study",
            condition_labels="control,treatment",
        )

        units = list(study.course_instance.course.units.prefetch_related("modules").order_by("order"))

        self.assertEqual([unit.title for unit in units], ["Before Study", "Main Study", "Post Study"])
        self.assertEqual([module.title for module in units[0].modules.all()], ["Consent", "Instructions", "Pretest"])
        self.assertEqual([module.title for module in units[1].modules.all()], ["Main Study Task"])
        self.assertEqual([module.title for module in units[2].modules.all()], ["Posttest", "Debrief"])

    def test_instructor_can_edit_default_study_form_modules(self):
        study = create_study_for_instructor(
            self.instructor,
            title="Editable Study",
            condition_labels="control,treatment",
        )
        self.client.force_login(self.instructor)

        course = study.course_instance.course
        consent = course.units.get(title="Before Study").modules.get(title="Consent")
        consent_question = consent.form.questions.first()
        payload = {
            "action": "update_structure",
        }
        for unit in course.units.prefetch_related("modules").all():
            payload.update({
                f"unit_{unit.id}_order": str(unit.order),
                f"unit_{unit.id}_title": unit.title,
                f"unit_{unit.id}_description": unit.description,
                f"unit_{unit.id}_visible": "1",
                f"unit_{unit.id}_locked": "1" if unit.is_locked else "0",
                f"unit_{unit.id}_rule_type": unit.unlock_rule_type,
                f"unit_{unit.id}_rule_target": unit.unlock_rule_target,
            })
            for module in unit.modules.all():
                payload.update({
                    f"module_{module.id}_order": str(module.order),
                    f"module_{module.id}_title": module.title,
                    f"module_{module.id}_description": module.description,
                    f"module_{module.id}_visible": "1",
                    f"module_{module.id}_locked": "1" if module.is_locked else "0",
                    f"module_{module.id}_rule_type": module.unlock_rule_type,
                    f"module_{module.id}_rule_target": module.unlock_rule_target,
                })
                if hasattr(module, "form"):
                    payload.update({
                        f"module_{module.id}_form_instructions": module.form.instructions,
                        f"module_{module.id}_form_submit_button_label": module.form.submit_button_label,
                    })

        payload.update({
            f"module_{consent.id}_title": "Custom Consent",
            f"module_{consent.id}_form_instructions": "Custom consent language.",
            f"module_{consent.id}_form_submit_button_label": "Agree And Begin",
            f"module_{consent.id}_question_{consent_question.id}_order": "10",
            f"module_{consent.id}_question_{consent_question.id}_prompt": "Do you consent to participate?",
            f"module_{consent.id}_question_{consent_question.id}_question_type": "single_choice",
            f"module_{consent.id}_question_{consent_question.id}_options": "Yes\nNo",
            f"module_{consent.id}_question_{consent_question.id}_required": "on",
            f"module_{consent.id}_form_new_question_1_prompt": "Participant initials",
            f"module_{consent.id}_form_new_question_1_question_type": "short_answer",
            f"module_{consent.id}_form_new_question_1_required": "on",
        })

        response = self.client.post(reverse("courses:course_configuration", args=[study.course_instance.id]), payload)

        self.assertEqual(response.status_code, 302)
        consent.refresh_from_db()
        consent.form.refresh_from_db()
        consent_question.refresh_from_db()
        self.assertEqual(consent.title, "Custom Consent")
        self.assertEqual(consent.form.instructions, "Custom consent language.")
        self.assertEqual(consent.form.submit_button_label, "Agree And Begin")
        self.assertEqual(consent_question.prompt, "Do you consent to participate?")
        self.assertEqual(consent_question.options, ["Yes", "No"])
        self.assertTrue(consent.form.questions.filter(prompt="Participant initials").exists())

    def test_anonymous_participant_profile_and_dashboard_redirect_to_study_sessions(self):
        source = RecruitmentSource.objects.create(
            course_instance=self.instance,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
        )
        self.client.get(reverse("recruitment:prolific_enter", args=[source.id]), {
            "PROLIFIC_PID": "5a9d64f5f6dfdd0001eaa73d",
            "STUDY_ID": "bbbbbbbbbbbbbbbbbbbbbbbb",
            "SESSION_ID": "cccccccccccccccccccccccc",
        })
        sessions_url = reverse("recruitment:sessions")

        self.assertRedirects(self.client.get(reverse("accounts:profile")), sessions_url)
        self.assertRedirects(self.client.get(reverse("dashboard:student_dashboard")), sessions_url)
        self.assertRedirects(self.client.get(reverse("courses:course_detail", args=[self.instance.id])), sessions_url)

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

    def test_participant_resume_opens_first_available_module(self):
        unit = self.course.units.create(title="Unit 1", order=10)
        module = unit.modules.create(title="First Module", order=10)
        source = RecruitmentSource.objects.create(
            course_instance=self.instance,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
        )
        self.client.get(reverse("recruitment:prolific_enter", args=[source.id]), {
            "PROLIFIC_PID": "5a9d64f5f6dfdd0001eaa73d",
            "STUDY_ID": "bbbbbbbbbbbbbbbbbbbbbbbb",
            "SESSION_ID": "cccccccccccccccccccccccc",
        })
        session = ParticipantSession.objects.get(recruitment_source=source)

        response = self.client.get(reverse("recruitment:resume_session", args=[session.uuid]))

        self.assertRedirects(
            response,
            reverse("courses:launch_iframe_module", args=[self.instance.id, module.id]),
            fetch_redirect_response=False,
        )

    def test_study_participant_progress_rows_include_study_context(self):
        study = create_study_for_instructor(
            self.instructor,
            title="Progress Context Study",
            condition_labels="control,treatment",
        )
        source = RecruitmentSource.objects.get(study=study, platform=RecruitmentSource.PLATFORM_PROLIFIC)

        self.client.get(reverse("recruitment:study_launch", args=[study.slug]), {
            "PROLIFIC_PID": "5a9d64f5f6dfdd0001eaa73d",
            "STUDY_ID": "bbbbbbbbbbbbbbbbbbbbbbbb",
            "SESSION_ID": "cccccccccccccccccccccccc",
        })
        session = ParticipantSession.objects.get(recruitment_source=source)
        progress_rows = ModuleProgress.objects.filter(enrollment=session.enrollment)

        self.assertGreater(progress_rows.count(), 0)
        self.assertFalse(progress_rows.filter(study_participant_session__isnull=True).exists())
        self.assertEqual(set(progress_rows.values_list("study_condition", flat=True)), {session.condition})

        first_module = study.course_instance.course.units.first().modules.first()
        first_question = first_module.form.questions.first()
        response = self.client.post(
            reverse("courses:launch_iframe_module", args=[study.course_instance.id, first_module.id]),
            {f"question_{first_question.id}": first_question.options[0]},
        )

        second_module = study.course_instance.course.units.first().modules.order_by("order", "id")[1]
        self.assertRedirects(
            response,
            reverse("courses:launch_iframe_module", args=[study.course_instance.id, second_module.id]),
            fetch_redirect_response=False,
        )
        module_progress = ModuleProgress.objects.get(enrollment=session.enrollment, module=first_module)
        self.assertTrue(module_progress.is_complete)
        self.assertEqual(module_progress.study_participant_session, session)
        event = ModuleProgressEvent.objects.filter(module_progress=module_progress, event_type="completion").first()
        self.assertIsNotNone(event)
        self.assertEqual(event.study_participant_session, session)
        self.assertEqual(event.study_condition, session.condition)

    def test_adaptive_branching_can_scope_failure_path_by_study_condition(self):
        study = self.make_study(title="Condition Branching Study")
        StudyCondition.objects.create(study=study, label="c3", name="Condition 3", order=30)
        source = RecruitmentSource.objects.create(
            study=study,
            platform=RecruitmentSource.PLATFORM_PROLIFIC,
            condition_strategy=RecruitmentSource.CONDITION_BALANCED,
        )
        self.course.plugin_config = {
            "plugins": {
                "adaptive_branching": {"enabled": True, "settings": {}},
            },
        }
        self.course.save(update_fields=["plugin_config"])
        unit = Unit.objects.create(course=self.course, title="Main Study", order=10)
        source_module = Module.objects.create(unit=unit, title="Problem A", order=10)
        c1_remediation = Module.objects.create(unit=unit, title="C1 Remediation", order=20, is_locked=True)
        c2_remediation = Module.objects.create(unit=unit, title="C2 Remediation", order=30, is_locked=True)
        c1_retry = Module.objects.create(unit=unit, title="Problem A Retry - C1", order=50, is_locked=True)
        c2_retry = Module.objects.create(unit=unit, title="Problem A Retry - C2", order=60, is_locked=True)
        ModuleBranchRule.objects.create(
            course=self.course,
            source_module=source_module,
            target_module=c1_remediation,
            condition_type=ModuleBranchRule.CONDITION_SCORE_LT,
            threshold=100,
            required_study_condition="control",
            priority=10,
        )
        ModuleBranchRule.objects.create(
            course=self.course,
            source_module=source_module,
            target_module=c2_remediation,
            condition_type=ModuleBranchRule.CONDITION_SCORE_LT,
            threshold=100,
            required_study_condition="treatment",
            priority=20,
        )
        ModuleBranchRule.objects.create(
            course=self.course,
            source_module=c1_remediation,
            target_module=c1_retry,
            condition_type=ModuleBranchRule.CONDITION_COMPLETED,
            required_study_condition="control",
            priority=30,
        )
        ModuleBranchRule.objects.create(
            course=self.course,
            source_module=c2_remediation,
            target_module=c2_retry,
            condition_type=ModuleBranchRule.CONDITION_COMPLETED,
            required_study_condition="treatment",
            priority=40,
        )

        self.client.get(reverse("recruitment:study_launch", args=[study.slug]), {
            "PROLIFIC_PID": "6a3951b4b326f99b82331661",
            "STUDY_ID": "6a584b56ace9629c9093ace6",
            "SESSION_ID": "0jfggbb63i5q",
        })
        session = ParticipantSession.objects.get(recruitment_source=source)
        self.assertEqual(session.condition, "control")
        progress, _created = ModuleProgress.get_or_create_progress(session.user, source_module, self.instance)

        apply_progress_snapshot(
            progress,
            source="test",
            progress=0.8,
            score=80,
            success=True,
            is_complete=False,
            event_type="outcome",
        )

        self.assertTrue(EnrollmentModuleUnlock.objects.filter(
            enrollment=session.enrollment,
            module=c1_remediation,
        ).exists())
        self.assertFalse(EnrollmentModuleUnlock.objects.filter(
            enrollment=session.enrollment,
            module=c2_remediation,
        ).exists())
        next_response = self.client.get(reverse("courses:next_accessible_module", args=[self.instance.id, source_module.id]))
        self.assertEqual(next_response.status_code, 200)
        self.assertEqual(next_response.json()["id"], c1_remediation.id)

        remediation_progress, _created = ModuleProgress.get_or_create_progress(session.user, c1_remediation, self.instance)
        apply_progress_snapshot(
            remediation_progress,
            source="test",
            progress=1.0,
            score=100,
            success=True,
            is_complete=True,
            event_type="completion",
        )

        self.assertTrue(EnrollmentModuleUnlock.objects.filter(
            enrollment=session.enrollment,
            module=c1_retry,
        ).exists())
        self.assertFalse(EnrollmentModuleUnlock.objects.filter(
            enrollment=session.enrollment,
            module=source_module,
        ).exists())

    def test_instructor_can_view_study_analytics_dashboard_and_export_csv(self):
        study = create_study_for_instructor(
            self.instructor,
            title="Analytics Study",
            condition_labels="control,treatment",
        )
        source = RecruitmentSource.objects.get(study=study, platform=RecruitmentSource.PLATFORM_PROLIFIC)

        self.client.get(reverse("recruitment:study_launch", args=[study.slug]), {
            "PROLIFIC_PID": "6a3951b4b326f99b82331661",
            "STUDY_ID": "6a584b56ace9629c9093ace6",
            "SESSION_ID": "0jfggbb63i5q",
        })
        session = ParticipantSession.objects.get(recruitment_source=source)
        first_module = study.course_instance.course.units.first().modules.first()
        first_question = first_module.form.questions.first()
        self.client.post(
            reverse("courses:launch_iframe_module", args=[study.course_instance.id, first_module.id]),
            {f"question_{first_question.id}": first_question.options[0]},
        )

        self.client.force_login(self.instructor)
        dashboard_response = self.client.get(reverse("dashboard:study_analytics_dashboard", args=[study.id]))
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertContains(dashboard_response, "Analytics Study")
        self.assertContains(dashboard_response, session.condition)
        self.assertContains(dashboard_response, "Consent")
        self.assertContains(dashboard_response, "Export CSV")

        csv_response = self.client.get(reverse("dashboard:export_study_analytics_csv", args=[study.id]))
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response["Content-Type"], "text/csv")
        csv_body = csv_response.content.decode()
        self.assertIn("participant_uuid,participant_label,external_pid", csv_body)
        self.assertIn("Consent", csv_body)
        self.assertIn("6a3951b4b326f99b82331661", csv_body)

    def test_instructor_can_clear_study_participants_and_progress(self):
        study = create_study_for_instructor(
            self.instructor,
            title="Resettable Study",
            condition_labels="control,treatment",
        )
        source = RecruitmentSource.objects.get(study=study, platform=RecruitmentSource.PLATFORM_PROLIFIC)

        self.client.get(reverse("recruitment:study_launch", args=[study.slug]), {
            "PROLIFIC_PID": "5a9d64f5f6dfdd0001eaa73d",
            "STUDY_ID": "bbbbbbbbbbbbbbbbbbbbbbbb",
            "SESSION_ID": "0jfggbb63i5q",
        })
        session = ParticipantSession.objects.get(recruitment_source=source)
        participant_user_id = session.user_id
        first_module = study.course_instance.course.units.first().modules.first()
        first_question = first_module.form.questions.first()
        self.client.post(
            reverse("courses:launch_iframe_module", args=[study.course_instance.id, first_module.id]),
            {f"question_{first_question.id}": first_question.options[0]},
        )

        self.assertTrue(ModuleProgress.objects.filter(enrollment=session.enrollment).exists())
        self.assertTrue(ModuleFormSubmission.objects.filter(enrollment=session.enrollment).exists())
        self.assertTrue(RecruitmentEntryLog.objects.filter(source=source).exists())

        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse("recruitment:reset_study_participation", args=[study.id]),
            {"confirm_reset": "RESET"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ParticipantSession.objects.filter(recruitment_source=source).exists())
        self.assertFalse(Enrollment.objects.filter(course_instance=study.course_instance).exists())
        self.assertFalse(ModuleProgress.objects.filter(module__unit__course=study.course_instance.course).exists())
        self.assertFalse(ModuleFormSubmission.objects.filter(form__module__unit__course=study.course_instance.course).exists())
        self.assertFalse(RecruitmentEntryLog.objects.filter(source=source).exists())
        self.assertFalse(get_user_model().objects.filter(id=participant_user_id).exists())
        self.assertTrue(RecruitmentSource.objects.filter(id=source.id, study=study).exists())
        self.assertTrue(Study.objects.filter(id=study.id).exists())

    def test_standard_course_student_progress_has_no_study_context(self):
        student = get_user_model().objects.create_user(username="ordinary-student", is_student=True)
        unit = self.course.units.create(title="Unit 1", order=10)
        module = unit.modules.create(title="First Module", order=10)
        enrollment = Enrollment.objects.create(student=student, course_instance=self.instance)

        module_progress = ModuleProgress.objects.get(enrollment=enrollment, module=module)

        self.assertIsNone(module_progress.study_participant_session)
        self.assertEqual(module_progress.study_condition, "")
