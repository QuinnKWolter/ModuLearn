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


def participant_course_redirect(user):
    participant_session = get_current_participant_session(user)
    if not participant_session:
        return None
    return redirect(
        "courses:course_detail",
        instance_id=participant_session.recruitment_source.course_instance_id,
    )


def user_can_access_participant_course(user, course_instance_id) -> bool:
    if not getattr(user, "is_anonymous_participant", False):
        return True
    participant_session = get_current_participant_session(user)
    return bool(
        participant_session
        and participant_session.recruitment_source.course_instance_id == course_instance_id
    )
