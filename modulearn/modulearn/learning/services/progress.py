from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone


PROGRESS_SCALE = (0.0, 1.0)
SCORE_SCALE = (0.0, 100.0)


def clamp(value: float | None, minimum: float, maximum: float) -> float | None:
    if value is None:
        return None
    return max(minimum, min(maximum, value))


def _coerce_score(value: float | int | None) -> float | None:
    if value is None:
        return None
    return clamp(float(value), *SCORE_SCALE)


def _coerce_progress(value: float | int | None) -> float | None:
    if value is None:
        return None
    return clamp(float(value), *PROGRESS_SCALE)


def log_module_progress_event(
    module_progress,
    *,
    event_type: str,
    source: str,
    payload: Any = None,
    progress: float | None = None,
    score: float | None = None,
    success: bool | None = None,
):
    from courses.models import ModuleProgressEvent

    return ModuleProgressEvent.objects.create(
        module_progress=module_progress,
        user=module_progress.user,
        module=module_progress.module,
        course_instance=getattr(getattr(module_progress, "enrollment", None), "course_instance", None),
        event_type=event_type,
        source=source,
        progress=_coerce_progress(progress if progress is not None else module_progress.progress),
        score=_coerce_score(score if score is not None else module_progress.score),
        success=module_progress.success if success is None else bool(success),
        payload=payload if payload is not None else {},
    )


def recompute_course_progress(enrollment, *, save: bool = True):
    from courses.models import CourseProgress, Module, ModuleProgress

    course_progress, _ = CourseProgress.objects.get_or_create(
        enrollment=enrollment,
        defaults={"total_modules": 0, "modules_completed": 0},
    )

    all_modules = Module.objects.filter(
        unit__course=enrollment.course_instance.course,
        unit__is_visible=True,
        is_visible=True,
    )
    total_modules = all_modules.count()
    progress_rows = ModuleProgress.objects.filter(enrollment=enrollment).select_related("module")
    progress_lookup = {row.module_id: row for row in progress_rows}

    total_progress = 0.0
    total_score = 0.0
    completed = 0

    for module in all_modules:
        progress = progress_lookup.get(module.id)
        if not progress:
            continue
        total_progress += progress.progress or 0.0
        total_score += progress.score or 0.0
        if progress.is_complete:
            completed += 1

    course_progress.total_modules = total_modules
    course_progress.modules_completed = completed
    course_progress.overall_progress = ((total_progress / total_modules) * 100.0) if total_modules else 0.0
    course_progress.overall_score = (total_score / total_modules) if total_modules else 0.0

    if total_modules and completed >= total_modules and course_progress.completed_at is None:
        course_progress.completed_at = timezone.now()

    if save:
        update_fields = [
            "total_modules",
            "modules_completed",
            "overall_progress",
            "overall_score",
            "last_accessed",
        ]
        if course_progress.completed_at:
            update_fields.append("completed_at")
        course_progress.save(update_fields=update_fields)
    return course_progress


@transaction.atomic
def apply_progress_snapshot(
    module_progress,
    *,
    source: str,
    progress: float | None = None,
    score: float | None = None,
    success: bool | None = None,
    is_complete: bool | None = None,
    payload: Any = None,
    event_type: str | None = None,
):
    progress = _coerce_progress(progress if progress is not None else module_progress.progress)
    score = _coerce_score(score if score is not None else module_progress.score)

    previous_complete = bool(module_progress.is_complete)
    previous_progress = module_progress.progress or 0.0
    previous_score = module_progress.score
    previous_success = bool(module_progress.success)

    if is_complete is None:
        is_complete = bool(progress is not None and progress >= 1.0)

    module_progress.progress = progress or 0.0
    module_progress.score = score
    module_progress.success = bool(success) if success is not None else bool(score is not None and score >= 70.0)
    module_progress.is_complete = bool(is_complete)

    changed = (
        previous_progress != module_progress.progress
        or previous_score != module_progress.score
        or previous_success != module_progress.success
        or previous_complete != module_progress.is_complete
    )

    if payload is not None:
        module_progress.state_data = payload
        changed = True

    timestamp = timezone.now()
    event_types: list[str] = []

    if module_progress.is_complete and module_progress.completed_at is None:
        module_progress.completed_at = timestamp
        event_types.append("completion")

    if previous_complete and not module_progress.is_complete:
        event_types.append("reopened")

    if event_type and not (event_type == "progress" and "completion" in event_types):
        event_types.insert(0, event_type)
    elif changed and "completion" not in event_types and "reopened" not in event_types:
        event_types.append("progress")

    if changed or payload is not None:
        module_progress.save()
        if module_progress.enrollment_id:
            course_progress = recompute_course_progress(module_progress.enrollment)
            if (
                course_progress.lis_result_sourcedid
                and course_progress.enrollment.course_instance.lis_outcome_service_url
            ):
                course_progress.submit_grade_to_canvas()

    for current_event_type in dict.fromkeys(event_types):
        event = log_module_progress_event(
            module_progress,
            event_type=current_event_type,
            source=source,
            payload=payload,
        )
        from modulearn.learning.services.adaptive_branching import handle_progress_event

        handle_progress_event(event)

    return module_progress


def record_module_launch(module_progress, *, source: str = "iframe"):
    return log_module_progress_event(module_progress, event_type="launch", source=source)
