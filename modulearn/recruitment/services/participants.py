from __future__ import annotations

from django.shortcuts import redirect

from recruitment.models import ParticipantSession


def get_current_participant_session(user):
    if not getattr(user, "is_authenticated", False):
        return None
    if not getattr(user, "is_anonymous_participant", False):
        return None
    return (
        ParticipantSession.objects.select_related(
            "recruitment_source",
            "recruitment_source__course_instance",
            "recruitment_source__course_instance__course",
            "enrollment",
        )
        .filter(user=user)
        .exclude(status__in=[
            ParticipantSession.STATUS_REJECTED,
            ParticipantSession.STATUS_ABANDONED,
        ])
        .order_by("-entered_at", "-id")
        .first()
    )


def get_participant_sessions(user):
    if not getattr(user, "is_authenticated", False):
        return []
    if not getattr(user, "is_anonymous_participant", False):
        return []
    return list(
        ParticipantSession.objects.select_related(
            "recruitment_source",
            "recruitment_source__course_instance",
            "recruitment_source__course_instance__course",
            "enrollment",
            "enrollment__course_progress",
        )
        .filter(user=user)
        .exclude(status__in=[
            ParticipantSession.STATUS_REJECTED,
            ParticipantSession.STATUS_ABANDONED,
        ])
        .order_by("-entered_at", "-id")
    )


def participant_course_redirect(user):
    if not get_current_participant_session(user):
        return None
    return redirect("recruitment:sessions")


def user_can_access_participant_course(user, course_instance_id) -> bool:
    if not getattr(user, "is_anonymous_participant", False):
        return True
    participant_session = get_current_participant_session(user)
    return bool(
        participant_session
        and participant_session.recruitment_source.course_instance_id == course_instance_id
    )


def get_participant_resume_module(participant_session):
    if not participant_session or not participant_session.enrollment:
        return None

    from courses.models import ModuleProgress
    from modulearn.learning.services.access_rules import evaluate_module_access, evaluate_unit_access

    enrollment = participant_session.enrollment
    course = participant_session.recruitment_source.course_instance.course
    if not course:
        return None

    first_accessible = None
    for unit in course.units.prefetch_related("modules").all():
        unit_state = evaluate_unit_access(unit, enrollment)
        if not unit_state.can_access:
            continue
        for module in unit.modules.all():
            module_state = evaluate_module_access(module, enrollment, unit_state=unit_state)
            if not module_state.can_access:
                continue
            if first_accessible is None:
                first_accessible = module
            progress = ModuleProgress.objects.filter(enrollment=enrollment, module=module).first()
            if not progress or not progress.is_complete:
                return module
    return first_accessible
