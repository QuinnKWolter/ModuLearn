from __future__ import annotations

from collections import OrderedDict

from courses.models import Module, ModuleProgress
from recruitment.models import ParticipantSession, Study


def build_study_analytics_context(study: Study) -> dict:
    course_instance = study.course_instance
    course = course_instance.course
    modules = list(
        Module.objects.filter(unit__course=course)
        .select_related("unit")
        .order_by("unit__order", "unit__id", "order", "id")
    )
    visible_module_count = sum(1 for module in modules if module.unit.is_visible and module.is_visible)

    sessions = list(
        ParticipantSession.objects.filter(recruitment_source__study=study)
        .select_related("recruitment_source", "user", "enrollment", "enrollment__course_progress")
        .order_by("condition", "entered_at", "id")
    )
    enrollment_ids = [session.enrollment_id for session in sessions if session.enrollment_id]
    progress_rows = (
        ModuleProgress.objects.filter(enrollment_id__in=enrollment_ids, module_id__in=[module.id for module in modules])
        .select_related("module", "module__unit")
        .order_by("module__unit__order", "module__order", "module__id")
    )
    progress_lookup = {
        (row.enrollment_id, row.module_id): row
        for row in progress_rows
    }

    condition_labels = [condition.label for condition in study.conditions.filter(is_active=True).order_by("order", "id")]
    condition_map = OrderedDict(
        (label, _empty_condition_summary(label))
        for label in condition_labels
    )
    condition_map.setdefault("unassigned", _empty_condition_summary("unassigned"))

    participants = []
    for index, session in enumerate(sessions, start=1):
        condition = session.condition or "unassigned"
        condition_map.setdefault(condition, _empty_condition_summary(condition))
        module_rows = []
        modules_completed = 0
        progress_total = 0.0
        latest_activity = None

        for module in modules:
            progress = progress_lookup.get((session.enrollment_id, module.id))
            progress_value = float(progress.progress or 0.0) if progress else 0.0
            if module.unit.is_visible and module.is_visible:
                progress_total += progress_value
            if progress and progress.is_complete:
                modules_completed += 1
            if progress and progress.last_accessed:
                latest_activity = max(latest_activity, progress.last_accessed) if latest_activity else progress.last_accessed
            module_rows.append({
                "unit_id": module.unit_id,
                "unit_title": module.unit.title,
                "module_id": module.id,
                "module_title": module.title,
                "module_type": module.display_type_label,
                "progress": progress_value,
                "progress_percent": round(progress_value * 100.0),
                "is_complete": bool(progress and progress.is_complete),
                "score": progress.score if progress and progress.score is not None else None,
                "attempts": progress.attempts if progress else 0,
                "success": bool(progress and progress.success),
                "first_accessed": progress.first_accessed if progress else None,
                "last_accessed": progress.last_accessed if progress else None,
            })

        course_progress = getattr(getattr(session, "enrollment", None), "course_progress", None)
        if course_progress:
            overall_progress = float(course_progress.overall_progress or 0.0)
            modules_completed = course_progress.modules_completed
            total_modules = course_progress.total_modules
        else:
            total_modules = visible_module_count
            overall_progress = (progress_total / total_modules * 100.0) if total_modules else 0.0

        participant = {
            "index": index,
            "session": session,
            "condition": condition,
            "participant_label": _participant_label(session),
            "external_pid": session.external_pid,
            "external_session_id": session.external_session_id,
            "status": session.status,
            "status_label": session.get_status_display(),
            "entered_at": session.entered_at,
            "completed_at": session.completed_at,
            "latest_activity": latest_activity,
            "overall_progress": overall_progress,
            "overall_progress_percent": round(overall_progress),
            "modules_completed": modules_completed,
            "total_modules": total_modules,
            "module_rows": module_rows,
        }
        participants.append(participant)

        condition_summary = condition_map[condition]
        condition_summary["participants"].append(participant)
        condition_summary["count"] += 1
        condition_summary["progress_total"] += overall_progress
        if session.is_finished:
            condition_summary["finished"] += 1

    for condition in condition_map.values():
        count = condition["count"]
        condition["avg_progress"] = round(condition["progress_total"] / count, 1) if count else 0.0
        condition["avg_progress_percent"] = round(condition["avg_progress"])
        condition["completion_rate"] = round((condition["finished"] / count) * 100.0, 1) if count else 0.0

    active_conditions = [condition for condition in condition_map.values() if condition["count"] or condition["label"] in condition_labels]
    total_progress = sum(participant["overall_progress"] for participant in participants)
    finished_count = sum(1 for participant in participants if participant["session"].is_finished)

    return {
        "study": study,
        "course": course,
        "course_instance": course_instance,
        "modules": modules,
        "participants": participants,
        "conditions": active_conditions,
        "summary": {
            "participant_count": len(participants),
            "condition_count": len(active_conditions),
            "avg_progress": round(total_progress / len(participants), 1) if participants else 0.0,
            "finished_count": finished_count,
            "module_count": visible_module_count,
        },
    }


def study_analytics_csv_rows(context: dict):
    for participant in context["participants"]:
        session = participant["session"]
        for module_row in participant["module_rows"]:
            yield {
                "participant_uuid": str(session.uuid),
                "participant_label": participant["participant_label"],
                "external_pid": session.external_pid,
                "external_study_id": session.external_study_id,
                "external_session_id": session.external_session_id,
                "condition": participant["condition"],
                "status": participant["status_label"],
                "entered_at": session.entered_at.isoformat() if session.entered_at else "",
                "completed_at": session.completed_at.isoformat() if session.completed_at else "",
                "unit": module_row["unit_title"],
                "module": module_row["module_title"],
                "module_type": module_row["module_type"],
                "progress_percent": module_row["progress_percent"],
                "is_complete": "yes" if module_row["is_complete"] else "no",
                "score": "" if module_row["score"] is None else module_row["score"],
                "attempts": module_row["attempts"],
                "success": "yes" if module_row["success"] else "no",
                "first_accessed": module_row["first_accessed"].isoformat() if module_row["first_accessed"] else "",
                "last_accessed": module_row["last_accessed"].isoformat() if module_row["last_accessed"] else "",
                "overall_progress_percent": participant["overall_progress_percent"],
                "modules_completed": participant["modules_completed"],
                "total_modules": participant["total_modules"],
            }


def _empty_condition_summary(label: str) -> dict:
    return {
        "label": label,
        "count": 0,
        "finished": 0,
        "progress_total": 0.0,
        "avg_progress": 0.0,
        "avg_progress_percent": 0,
        "completion_rate": 0.0,
        "participants": [],
    }


def _participant_label(session: ParticipantSession) -> str:
    if session.external_pid:
        return f"P-{session.external_pid[-6:]}"
    if session.user_id:
        return f"User {session.user_id}"
    return f"Session {session.id}"
