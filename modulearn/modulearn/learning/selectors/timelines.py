from __future__ import annotations

from django.utils import timezone


DEFAULT_TIMELINE_EVENTS = ("completion", "outcome", "reopened", "progress")


def _serialize_event(event):
    course_instance = getattr(event, "course_instance", None)
    course = getattr(course_instance, "course", None)
    user = getattr(event, "user", None)
    learner_name = (
        getattr(user, "full_name", None)
        or getattr(user, "get_full_name", lambda: "")()
        or getattr(user, "username", "")
    )
    learner_name = str(learner_name).strip()
    learner_email = (getattr(user, "email", "") or "").strip()
    learner_initials = "".join(part[0] for part in learner_name.split()[:2]).upper()
    if not learner_initials and getattr(user, "username", ""):
        learner_initials = str(user.username)[:2].upper()
    return {
        "id": event.id,
        "event_type": event.event_type,
        "source": event.source,
        "created_at": timezone.localtime(event.created_at),
        "progress": event.progress,
        "progress_percent": round(float(event.progress or 0) * 100),
        "score": event.score,
        "success": event.success,
        "module_title": event.module.title if event.module_id else "",
        "learner_name": learner_name,
        "learner_username": getattr(user, "username", ""),
        "learner_email": learner_email,
        "learner_initials": learner_initials,
        "course_title": course.title if course else "",
        "course_instance_id": course_instance.id if course_instance else None,
        "group_name": course_instance.group_name if course_instance else "",
    }


def _base_queryset():
    from courses.models import ModuleProgressEvent

    return ModuleProgressEvent.objects.select_related(
        "module",
        "course_instance",
        "course_instance__course",
        "user",
    ).order_by("-created_at")


def _visible_timeline_events(queryset):
    # Completion snapshots can emit both a progress=100% event and a completion
    # event. Keep the semantically useful completion entry in every timeline.
    return queryset.exclude(event_type="progress", progress__gte=1.0)


def get_student_timeline(user, *, limit: int = 12, event_types=DEFAULT_TIMELINE_EVENTS):
    queryset = _base_queryset().filter(user=user)
    if event_types:
        queryset = queryset.filter(event_type__in=event_types)
    queryset = _visible_timeline_events(queryset)
    return [_serialize_event(event) for event in queryset[:limit]]


def get_course_timeline_for_student(course_instance, user, *, limit: int = 12, event_types=DEFAULT_TIMELINE_EVENTS):
    queryset = _base_queryset().filter(user=user, course_instance=course_instance)
    if event_types:
        queryset = queryset.filter(event_type__in=event_types)
    queryset = _visible_timeline_events(queryset)
    return [_serialize_event(event) for event in queryset[:limit]]


def get_course_instance_recent_activity(course_instance, *, limit: int = 12, event_types=DEFAULT_TIMELINE_EVENTS):
    queryset = _base_queryset().filter(course_instance=course_instance)
    if event_types:
        queryset = queryset.filter(event_type__in=event_types)
    queryset = _visible_timeline_events(queryset)
    return [_serialize_event(event) for event in queryset[:limit]]
