from __future__ import annotations

import uuid

from django.db import transaction

from courses.models import (
    Course,
    CourseInstance,
    CourseProgress,
    Enrollment,
    EnrollmentModuleUnlock,
    Module,
    ModuleAccessLog,
    ModuleForm,
    ModuleFormQuestion,
    ModuleFormSubmission,
    ModuleProgress,
    Unit,
)
from recruitment.models import (
    ParticipantSession,
    RecruitmentAssignmentSlot,
    RecruitmentEntryLog,
    RecruitmentSource,
    Study,
    StudyCondition,
)


DEFAULT_STUDY_CONDITIONS = ["control", "treatment"]


DEFAULT_STUDY_UNITS = [
    {
        "title": "Before Study",
        "description": "Consent, instructions, and baseline measures before the main task.",
        "modules": [
            {
                "title": "Consent",
                "description": "Participant consent and eligibility confirmation.",
                "module_type": Module.MODULE_TYPE_STUDY_CONSENT,
                "instructions": (
                    "Review the study information carefully. Submit this form only if you agree to participate."
                ),
                "submit_button_label": "I Consent",
                "questions": [
                    {
                        "prompt": "I have read the study information and agree to participate.",
                        "question_type": ModuleFormQuestion.TYPE_SINGLE_CHOICE,
                        "options": ["I agree"],
                        "required": True,
                    },
                ],
            },
            {
                "title": "Instructions",
                "description": "Study instructions shown before the task sequence begins.",
                "module_type": Module.MODULE_TYPE_STUDY_INSTRUCTIONS,
                "instructions": "Read the instructions for this study. Submit when you are ready to continue.",
                "submit_button_label": "Continue",
                "questions": [
                    {
                        "prompt": "I understand the instructions and am ready to begin.",
                        "question_type": ModuleFormQuestion.TYPE_SINGLE_CHOICE,
                        "options": ["Ready"],
                        "required": True,
                    },
                ],
            },
            {
                "title": "Pretest",
                "description": "Baseline questions or an external pretest placeholder.",
                "module_type": Module.MODULE_TYPE_STUDY_PRETEST,
                "instructions": "Complete the pretest items before beginning the main study tasks.",
                "submit_button_label": "Submit Pretest",
                "questions": [
                    {
                        "prompt": "Pretest placeholder response",
                        "question_type": ModuleFormQuestion.TYPE_SHORT_ANSWER,
                        "required": True,
                    },
                ],
            },
        ],
    },
    {
        "title": "Main Study",
        "description": "Primary experimental task sequence.",
        "modules": [
            {
                "title": "Main Study Task",
                "description": "Replace this placeholder with the first interactive problem or study module.",
                "module_type": Module.MODULE_TYPE_FORM,
                "instructions": "This placeholder marks where the main experimental task sequence begins.",
                "submit_button_label": "Mark Placeholder Complete",
                "questions": [
                    {
                        "prompt": "Instructor setup note: replace this module with the first study activity.",
                        "question_type": ModuleFormQuestion.TYPE_SINGLE_CHOICE,
                        "options": ["I understand this placeholder should be replaced."],
                        "required": True,
                    },
                ],
            },
        ],
    },
    {
        "title": "Post Study",
        "description": "Post-study measures, debrief, and completion flow.",
        "modules": [
            {
                "title": "Posttest",
                "description": "Required post-study questions or external posttest placeholder.",
                "module_type": Module.MODULE_TYPE_STUDY_POSTTEST,
                "instructions": "Complete the posttest before receiving study completion credit.",
                "submit_button_label": "Submit Posttest",
                "questions": [
                    {
                        "prompt": "Posttest placeholder response",
                        "question_type": ModuleFormQuestion.TYPE_SHORT_ANSWER,
                        "required": True,
                    },
                ],
            },
            {
                "title": "Debrief",
                "description": "Final debrief and completion instructions.",
                "module_type": Module.MODULE_TYPE_STUDY_DEBRIEF,
                "instructions": "Read the debrief. The final study link can return you to Prolific for credit.",
                "submit_button_label": "Finish Debrief",
                "questions": [
                    {
                        "prompt": "I have read the debrief.",
                        "question_type": ModuleFormQuestion.TYPE_SINGLE_CHOICE,
                        "options": ["Complete"],
                        "required": True,
                    },
                ],
            },
        ],
    },
]


def parse_condition_labels(raw_labels: str) -> list[str]:
    labels = []
    for raw_label in (raw_labels or "").replace("\n", ",").split(","):
        label = raw_label.strip().lower().replace(" ", "_")
        if label and label not in labels:
            labels.append(label[:32])
    return labels or list(DEFAULT_STUDY_CONDITIONS)


@transaction.atomic
def create_study_for_instructor(
    instructor,
    *,
    title: str,
    description: str = "",
    version_label: str = "v1.0",
    condition_labels: str = "",
) -> Study:
    title = (title or "").strip() or "Untitled Study"
    description = (description or "").strip()
    version_label = (version_label or "").strip() or "v1.0"
    course = Course.objects.create(
        id=f"study-{uuid.uuid4().hex[:16]}",
        title=title,
        description=description,
        is_locked_for_research=True,
    )
    course.instructors.add(instructor)

    course_instance = CourseInstance.objects.create(
        course=course,
        group_name=f"{title} Participants",
    )
    course_instance.instructors.add(instructor)

    study = Study.objects.create(
        title=title,
        description=description,
        version_label=version_label,
        course_instance=course_instance,
    )
    study.instructors.add(instructor)

    for index, label in enumerate(parse_condition_labels(condition_labels), start=1):
        StudyCondition.objects.create(
            study=study,
            label=label,
            name=label.replace("_", " ").title(),
            order=index * 10,
        )

    RecruitmentSource.objects.create(
        study=study,
        platform=RecruitmentSource.PLATFORM_PROLIFIC,
        label="Prolific",
        is_active=True,
        condition_strategy=RecruitmentSource.CONDITION_BALANCED,
        condition_labels="",
    )

    previous_module = None
    for unit_index, unit_definition in enumerate(DEFAULT_STUDY_UNITS, start=1):
        unit = Unit.objects.create(
            course=course,
            title=unit_definition["title"],
            description=unit_definition["description"],
            order=unit_index * 10,
            is_visible=True,
        )
        for module_index, definition in enumerate(unit_definition["modules"], start=1):
            unlock_rule = {}
            is_locked = False
            if previous_module:
                is_locked = True
                unlock_rule = {
                    "operator": "all",
                    "conditions": [
                        {"type": "module_completed", "target_id": str(previous_module.id)}
                    ],
                }
            module = Module.objects.create(
                unit=unit,
                title=definition["title"],
                description=definition["description"],
                module_type=definition["module_type"],
                order=module_index * 10,
                is_visible=True,
                is_locked=is_locked,
                unlock_rule=unlock_rule,
                content_data={"study_default": True, "study_step": definition["module_type"]},
            )
            module_form = ModuleForm.objects.create(
                module=module,
                instructions=definition["instructions"],
                allow_resubmission=False,
                submit_button_label=definition["submit_button_label"],
            )
            for question_index, question in enumerate(definition["questions"], start=1):
                ModuleFormQuestion.objects.create(
                    form=module_form,
                    prompt=question["prompt"],
                    question_type=question["question_type"],
                    required=question.get("required", True),
                    options=question.get("options", []),
                    order=question_index * 10,
                )
            previous_module = module

    return study


@transaction.atomic
def clear_study_participation(study: Study) -> dict[str, int]:
    """Delete participant/run data for a study while preserving the study setup."""
    source_ids = list(study.recruitment_sources.values_list("id", flat=True))
    if not source_ids:
        return {
            "participants": 0,
            "enrollments": 0,
            "progress_rows": 0,
            "form_submissions": 0,
            "access_logs": 0,
            "entry_logs": 0,
            "users": 0,
        }

    sessions = ParticipantSession.objects.filter(recruitment_source_id__in=source_ids)
    participant_count = sessions.count()
    enrollment_ids = list(
        sessions.exclude(enrollment_id__isnull=True).values_list("enrollment_id", flat=True).distinct()
    )
    user_ids = list(
        sessions.filter(user__is_anonymous_participant=True)
        .exclude(user_id__isnull=True)
        .values_list("user_id", flat=True)
        .distinct()
    )
    user_model = study.instructors.model

    entry_log_count = RecruitmentEntryLog.objects.filter(source_id__in=source_ids).count()
    access_log_count = ModuleAccessLog.objects.filter(enrollment_id__in=enrollment_ids).count()
    form_submission_count = ModuleFormSubmission.objects.filter(enrollment_id__in=enrollment_ids).count()
    progress_count = ModuleProgress.objects.filter(enrollment_id__in=enrollment_ids).count()
    enrollment_count = len(enrollment_ids)
    user_count = user_model.objects.filter(id__in=user_ids, is_anonymous_participant=True).count()

    RecruitmentAssignmentSlot.objects.filter(source_id__in=source_ids).update(
        claimed_by=None,
        claimed_at=None,
    )

    RecruitmentEntryLog.objects.filter(source_id__in=source_ids).delete()
    ModuleAccessLog.objects.filter(enrollment_id__in=enrollment_ids).delete()
    ModuleFormSubmission.objects.filter(enrollment_id__in=enrollment_ids).delete()
    ModuleProgress.objects.filter(enrollment_id__in=enrollment_ids).delete()
    CourseProgress.objects.filter(enrollment_id__in=enrollment_ids).delete()
    EnrollmentModuleUnlock.objects.filter(enrollment_id__in=enrollment_ids).delete()
    Enrollment.objects.filter(id__in=enrollment_ids).delete()

    sessions.delete()

    user_model.objects.filter(
        id__in=user_ids,
        is_anonymous_participant=True,
    ).delete()

    return {
        "participants": participant_count,
        "enrollments": enrollment_count,
        "progress_rows": progress_count,
        "form_submissions": form_submission_count,
        "access_logs": access_log_count,
        "entry_logs": entry_log_count,
        "users": user_count,
    }
