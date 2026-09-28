from __future__ import annotations

from django.shortcuts import redirect

from recruitment.models import ParticipantSession


def get_current_participant_session(user):
    if getattr(user, "is_instructor", False):
        return None
    if not getattr(user, "is_authenticated", False):
        return None
    if not getattr(user, "is_anonymous_participant", False):
        return None
    return (
        ParticipantSession.objects.select_related(
            "recruitment_source",
            "recruitment_source__study",
            "recruitment_source__study__course_instance",
            "recruitment_source__study__course_instance__course",
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
    if getattr(user, "is_instructor", False):
        return []
    if not getattr(user, "is_authenticated", False):
        return []
    if not getattr(user, "is_anonymous_participant", False):
        return []
    return list(
        ParticipantSession.objects.select_related(
            "recruitment_source",
            "recruitment_source__study",
            "recruitment_source__study__course_instance",
            "recruitment_source__study__course_instance__course",
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
    participant_session = get_current_participant_session(user)
    if not participant_session:
        return None
    if participant_session.is_finished:
        return redirect("recruitment:already_completed", session_uuid=participant_session.uuid)
    return redirect("recruitment:resume_session", session_uuid=participant_session.uuid)


def user_can_access_participant_course(user, course_instance_id) -> bool:
    # This only bypasses participant confinement; normal course ownership and
    # enrollment checks still apply at the caller.
    if getattr(user, "is_instructor", False):
        return True
    if not getattr(user, "is_anonymous_participant", False):
        return True
    participant_session = get_current_participant_session(user)
    course_instance = participant_session.recruitment_source.resolved_course_instance if participant_session else None
    return bool(
        participant_session
        and course_instance
        and course_instance.id == course_instance_id
    )


def get_participant_resume_module(participant_session):
    if not participant_session or not participant_session.enrollment:
        return None

    from courses.models import EnrollmentModuleUnlock, ModuleProgress
    from modulearn.learning.services.access_rules import evaluate_module_access, evaluate_unit_access

    enrollment = participant_session.enrollment
    course_instance = participant_session.recruitment_source.resolved_course_instance
    course = course_instance.course if course_instance else None
    if not course:
        return None

    accessible_modules = []
    for unit in course.units.prefetch_related("modules").all():
        unit_state = evaluate_unit_access(unit, enrollment)
        if not unit_state.can_access:
            continue
        for module in unit.modules.all():
            module_state = evaluate_module_access(module, enrollment, unit_state=unit_state)
            if not module_state.can_access:
                continue
            accessible_modules.append(module)

    if not accessible_modules:
        return None

    progress_lookup = {
        progress.module_id: progress
        for progress in ModuleProgress.objects.filter(
            enrollment=enrollment,
            module_id__in=[module.id for module in accessible_modules],
        )
    }
    latest_progress = (
        ModuleProgress.objects.filter(
            enrollment=enrollment,
            module_id__in=[module.id for module in accessible_modules],
        )
        .select_related("module", "module__unit")
        .order_by("-last_accessed", "-id")
        .first()
    )

    if latest_progress:
        ordered_ids = [module.id for module in accessible_modules]
        latest_index = ordered_ids.index(latest_progress.module_id)
        for module in accessible_modules[:latest_index]:
            progress = progress_lookup.get(module.id)
            if not progress or not progress.is_complete:
                return module

        if latest_progress.is_complete:
            for module in accessible_modules[latest_index + 1:]:
                progress = progress_lookup.get(module.id)
                if not progress or not progress.is_complete:
                    return module
        else:
            dynamic_target = (
                EnrollmentModuleUnlock.objects.filter(
                    enrollment=enrollment,
                    source_module_id=latest_progress.module_id,
                    module_id__in=ordered_ids,
                    source_rule__active=True,
                )
                .select_related("module", "module__unit", "source_rule")
                .order_by("source_rule__priority", "module__unit__order", "module__order", "module_id")
                .first()
            )
            if dynamic_target:
                return dynamic_target.module
            return latest_progress.module

    for module in accessible_modules:
        progress = progress_lookup.get(module.id)
        if not progress or not progress.is_complete:
            return module
    return accessible_modules[0]
