from __future__ import annotations

from courses.models import CourseProgress, Enrollment, ModuleProgress
from django.db.models import Q

from .timelines import get_course_timeline_for_student
from modulearn.learning.services.access_rules import evaluate_module_access, evaluate_unit_access
from modulearn.learning.services.course_plugins import enabled_course_plugins


def build_course_detail_context(user, course_instance):
    course = course_instance.course
    is_instructor = course_instance.instructors.filter(id=user.id).exists()
    enrollment = None
    is_enrolled = False
    course_progress = None
    module_progress_data = {}
    timeline = []
    participant_session = None

    if getattr(user, "is_authenticated", False) and not is_instructor:
        enrollment = Enrollment.objects.filter(
            student=user,
            course_instance=course_instance,
            active=True,
        ).first()
        is_enrolled = enrollment is not None

        if is_enrolled:
            course_progress = CourseProgress.objects.get(enrollment=enrollment)
            module_progresses = ModuleProgress.objects.filter(enrollment=enrollment).select_related("module")
            module_progress_data = {
                module_progress.module.id: {
                    "is_complete": bool(module_progress.is_complete),
                    "score": module_progress.score,
                    "progress": module_progress.progress,
                    "completed_at": module_progress.completed_at,
                }
                for module_progress in module_progresses
            }
            timeline = get_course_timeline_for_student(course_instance, user, limit=12)
            if getattr(user, "is_anonymous_participant", False):
                participant_session = enrollment.participant_sessions.filter(
                    Q(recruitment_source__course_instance=course_instance)
                    | Q(recruitment_source__study__course_instance=course_instance)
                ).select_related("recruitment_source").first()

    units = list(course.units.prefetch_related("modules", "modules__form").all())
    unit_cards = []
    for unit_index, unit in enumerate(units):
        unit_state = evaluate_unit_access(unit, enrollment, include_hidden=is_instructor)
        if not is_instructor and not unit_state.is_visible:
            continue

        module_items = []
        module_count = 0
        completed_count = 0
        progress_sum = 0.0
        has_progress = False

        for module in unit.modules.all():
            module_state = evaluate_module_access(
                module,
                enrollment,
                unit_state=unit_state,
                include_hidden=is_instructor,
            )
            if not is_instructor and not module_state.is_visible:
                continue

            module_count += 1
            progress_data = module_progress_data.get(module.id, {})
            progress_value = float(progress_data.get("progress") or 0.0)
            is_complete = bool(progress_data.get("is_complete")) or progress_value >= 1.0
            if is_complete:
                progress_value = 1.0
            progress_value = max(0.0, min(progress_value, 1.0))
            progress_percent = round(progress_value * 100)

            if progress_value > 0:
                has_progress = True
            if not module_state.can_access and not is_instructor:
                status = "Locked"
                status_class = "is-locked"
                icon_class = "fa-solid fa-lock"
            elif is_complete:
                completed_count += 1
                status = "Done"
                status_class = "is-complete"
                icon_class = "fa-solid fa-check"
            elif progress_value > 0:
                status = "In Progress"
                status_class = "is-active"
                icon_class = "fa-solid fa-play"
            else:
                status = "To-Do"
                status_class = "is-todo"
                icon_class = "fa-regular fa-circle"

            progress_sum += progress_value
            module_items.append({
                "id": module.id,
                "title": module.title,
                "progress_percent": progress_percent,
                "status": status,
                "status_class": status_class,
                "icon_class": icon_class,
                "is_complete": is_complete,
                "completed_at": progress_data.get("completed_at"),
                "module_type": module.module_type,
                "is_visible": module.is_visible,
                "is_locked": module.is_locked,
                "can_access": is_instructor or module_state.can_access,
                "lock_reason": module_state.reason,
                "type_label": module.display_type_label,
            })

        unit_percent = round((progress_sum / module_count) * 100) if module_count else 0
        is_unit_complete = module_count > 0 and completed_count == module_count
        unit_cards.append({
            "unit": unit,
            "modules": module_items,
            "module_count": module_count,
            "completed_count": completed_count,
            "progress_percent": unit_percent,
            "is_complete": is_unit_complete,
            "is_expanded": (unit_index == 0 or has_progress) and not is_unit_complete and (is_instructor or unit_state.can_access),
            "is_visible": unit.is_visible,
            "is_locked": unit.is_locked,
            "can_access": is_instructor or unit_state.can_access,
            "lock_reason": unit_state.reason,
        })

    return {
        "course": course,
        "current_instance": course_instance,
        "units": units,
        "unit_cards": unit_cards,
        "is_instructor": is_instructor,
        "is_enrolled": is_enrolled,
        "enrollment": enrollment,
        "course_progress": course_progress,
        "module_progress_data": module_progress_data,
        "timeline": timeline,
        "participant_session": participant_session,
        "course_plugins": enabled_course_plugins(course),
    }
