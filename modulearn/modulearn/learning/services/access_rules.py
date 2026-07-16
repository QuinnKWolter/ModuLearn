from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import Max, Q


@dataclass(frozen=True)
class AccessState:
    is_visible: bool
    is_unlocked: bool
    reason: str = ""

    @property
    def can_access(self) -> bool:
        return self.is_visible and self.is_unlocked


def empty_rule() -> dict[str, Any]:
    return {"mode": "all", "conditions": []}


def build_unlock_rule(rule_type: str | None, target_id: str | int | None = None) -> dict[str, Any]:
    rule_type = (rule_type or "none").strip()
    if rule_type == "none":
        return {}
    condition: dict[str, Any] = {"type": rule_type}
    if target_id not in (None, ""):
        if rule_type == "condition_equals":
            condition["target_id"] = str(target_id).strip()
        else:
            condition["target_id"] = int(target_id)
    return {"mode": "all", "conditions": [condition]}


def next_order_for_unit(course) -> int:
    from courses.models import Unit

    value = Unit.objects.filter(course=course).aggregate(Max("order"))["order__max"]
    return (value or 0) + 10


def next_order_for_module(unit) -> int:
    from courses.models import Module

    value = Module.objects.filter(unit=unit).aggregate(Max("order"))["order__max"]
    return (value or 0) + 10


def sync_module_progress_for_course(module):
    from courses.models import Enrollment, ModuleProgress

    if not module.unit_id:
        return

    enrollments = Enrollment.objects.filter(course_instance__course=module.unit.course)
    existing = set(
        ModuleProgress.objects.filter(module=module, enrollment__in=enrollments)
        .values_list("enrollment_id", flat=True)
    )
    rows = []
    for enrollment in enrollments:
        if enrollment.id in existing:
            continue
        participant_session = ModuleProgress.participant_session_for_enrollment(enrollment)
        rows.append(
            ModuleProgress(
                user=enrollment.student,
                module=module,
                enrollment=enrollment,
                study_participant_session=participant_session,
                study_condition=getattr(participant_session, "condition", "") or "",
            )
        )
    if rows:
        ModuleProgress.objects.bulk_create(rows, ignore_conflicts=True)


def log_module_access(user, module, course_instance, *, event_type: str = "view", metadata: dict[str, Any] | None = None):
    from courses.models import Enrollment, ModuleAccessLog

    enrollment = Enrollment.objects.filter(student=user, course_instance=course_instance).first()
    return ModuleAccessLog.objects.create(
        user=user,
        enrollment=enrollment,
        module=module,
        course_instance=course_instance,
        event_type=event_type,
        metadata=metadata or {},
    )


def evaluate_unit_access(unit, enrollment, *, include_hidden: bool = False) -> AccessState:
    if not unit.is_visible and not include_hidden:
        return AccessState(False, False, "Hidden by instructor")
    if not unit.is_locked:
        return AccessState(True, True)
    if _rule_passes(unit.unlock_rule, enrollment, subject_unit=unit):
        return AccessState(True, True)
    return AccessState(True, False, _rule_reason(unit.unlock_rule, subject_unit=unit) or "Locked until the instructor conditions are met")


def evaluate_module_access(module, enrollment, *, unit_state: AccessState | None = None, include_hidden: bool = False) -> AccessState:
    if not module.is_visible and not include_hidden:
        return AccessState(False, False, "Hidden by instructor")
    has_dynamic_unlock = _has_dynamic_module_unlock(enrollment, module)
    if unit_state is not None and not unit_state.can_access:
        if unit_state.is_visible and has_dynamic_unlock:
            return AccessState(True, True)
        return AccessState(unit_state.is_visible, False, unit_state.reason or "Unit is locked")
    if not module.is_locked:
        return AccessState(True, True)
    if has_dynamic_unlock:
        return AccessState(True, True)
    if _rule_passes(module.unlock_rule, enrollment, subject_module=module):
        return AccessState(True, True)
    return AccessState(
        True,
        False,
        _rule_reason(module.unlock_rule, subject_module=module)
        or _branch_reason(module)
        or "Locked until the instructor conditions are met",
    )


def _rule_passes(rule: dict[str, Any] | None, enrollment, *, subject_unit=None, subject_module=None) -> bool:
    if not enrollment:
        return False
    rule = rule or {}
    conditions = rule.get("conditions") or []
    if not conditions:
        return False

    results = [
        _condition_passes(condition, enrollment, subject_unit=subject_unit, subject_module=subject_module)
        for condition in conditions
    ]
    return any(results) if rule.get("mode") == "any" else all(results)


def _has_dynamic_module_unlock(enrollment, module) -> bool:
    try:
        from modulearn.learning.services.adaptive_branching import has_dynamic_module_unlock

        return has_dynamic_module_unlock(enrollment, module)
    except Exception:
        return False


def _condition_passes(condition: dict[str, Any], enrollment, *, subject_unit=None, subject_module=None) -> bool:
    condition_type = condition.get("type")
    target_id = condition.get("target_id")

    if condition_type in {"module_accessed", "resource_accessed"}:
        return _module_accessed(enrollment, target_id)
    if condition_type in {"module_completed", "form_completed", "survey_completed", "quiz_completed"}:
        return _module_completed(enrollment, target_id)
    if condition_type == "unit_accessed":
        return _unit_accessed(enrollment, target_id)
    if condition_type == "unit_completed":
        return _unit_completed(enrollment, target_id)
    if condition_type == "condition_equals":
        return _participant_condition(enrollment) == str(target_id or "")
    if condition_type == "previous_unit_accessed":
        unit = subject_unit or getattr(subject_module, "unit", None)
        previous_unit = _previous_unit(unit)
        return _unit_accessed(enrollment, previous_unit.id) if previous_unit else True
    if condition_type == "previous_unit_completed":
        unit = subject_unit or getattr(subject_module, "unit", None)
        previous_unit = _previous_unit(unit)
        return _unit_completed(enrollment, previous_unit.id) if previous_unit else True

    return False


def _participant_condition(enrollment) -> str:
    if not enrollment:
        return ""
    try:
        session = enrollment.participant_sessions.filter(
            Q(recruitment_source__course_instance=enrollment.course_instance)
            | Q(recruitment_source__study__course_instance=enrollment.course_instance)
        ).order_by("-entered_at").first()
    except Exception:
        session = None
    return getattr(session, "condition", "") or ""


def _module_accessed(enrollment, module_id) -> bool:
    from courses.models import ModuleAccessLog

    if not module_id:
        return False
    return ModuleAccessLog.objects.filter(
        enrollment=enrollment,
        module_id=module_id,
        event_type__in=[
            ModuleAccessLog.EVENT_VIEW,
            ModuleAccessLog.EVENT_LAUNCH,
            ModuleAccessLog.EVENT_DOWNLOAD,
            ModuleAccessLog.EVENT_FORM_SUBMIT,
        ],
    ).exists()


def _module_completed(enrollment, module_id) -> bool:
    from courses.models import ModuleProgress

    if not module_id:
        return False
    return ModuleProgress.objects.filter(enrollment=enrollment, module_id=module_id, is_complete=True).exists()


def _unit_modules(unit_id):
    from courses.models import Module

    return Module.objects.filter(unit_id=unit_id, is_visible=True).order_by("order", "id")


def _unit_accessed(enrollment, unit_id) -> bool:
    modules = list(_unit_modules(unit_id))
    if not modules:
        return False
    return all(_module_accessed(enrollment, module.id) for module in modules)


def _unit_completed(enrollment, unit_id) -> bool:
    modules = list(_unit_modules(unit_id))
    if not modules:
        return False
    return all(_module_completed(enrollment, module.id) for module in modules)


def _previous_unit(unit):
    if not unit or not unit.course_id:
        return None
    return (
        unit.course.units.filter(is_visible=True)
        .filter(order__lt=unit.order)
        .order_by("-order", "-id")
        .first()
        or unit.course.units.filter(is_visible=True, order=unit.order, id__lt=unit.id).order_by("-id").first()
    )


def _rule_reason(rule: dict[str, Any] | None, *, subject_unit=None, subject_module=None) -> str:
    conditions = (rule or {}).get("conditions") or []
    if not conditions:
        return ""
    condition = conditions[0]
    condition_type = condition.get("type")
    target_id = condition.get("target_id")

    if condition_type in {"module_accessed", "resource_accessed"}:
        target = _module_title(target_id)
        return f"Unlocks after {target} is accessed" if target else "Unlocks after the selected module is accessed"
    if condition_type in {"module_completed", "form_completed", "survey_completed", "quiz_completed"}:
        target = _module_title(target_id)
        return f"Unlocks after {target} is completed" if target else "Unlocks after the selected module is completed"
    if condition_type == "unit_accessed":
        target = _unit_title(target_id)
        return f"Unlocks after {target} has been fully accessed" if target else "Unlocks after the selected unit has been fully accessed"
    if condition_type == "unit_completed":
        target = _unit_title(target_id)
        return f"Unlocks after {target} is completed" if target else "Unlocks after the selected unit is completed"
    if condition_type == "previous_unit_accessed":
        previous_unit = _previous_unit(subject_unit or getattr(subject_module, "unit", None))
        return (
            f"Unlocks after {previous_unit.title} has been fully accessed"
            if previous_unit
            else "Unlocks after the previous unit has been fully accessed"
        )
    if condition_type == "previous_unit_completed":
        previous_unit = _previous_unit(subject_unit or getattr(subject_module, "unit", None))
        return (
            f"Unlocks after {previous_unit.title} is completed"
            if previous_unit
            else "Unlocks after the previous unit is completed"
        )
    if condition_type == "condition_equals":
        return f"Unlocks for participants in condition {target_id}" if target_id else "Unlocks for participants assigned to the selected condition"
    return ""


def _module_title(module_id) -> str:
    if not module_id:
        return ""
    try:
        from courses.models import Module

        return Module.objects.filter(id=module_id).values_list("title", flat=True).first() or ""
    except Exception:
        return ""


def _unit_title(unit_id) -> str:
    if not unit_id:
        return ""
    try:
        from courses.models import Unit

        return Unit.objects.filter(id=unit_id).values_list("title", flat=True).first() or ""
    except Exception:
        return ""


def _branch_reason(module) -> str:
    if not module or not getattr(module, "id", None):
        return ""
    try:
        from courses.models import ModuleBranchRule

        rules = list(
            ModuleBranchRule.objects.filter(target_module=module, active=True)
            .select_related("source_module")
            .order_by("priority", "id")[:2]
        )
    except Exception:
        return ""
    if not rules:
        return ""

    def describe(rule):
        source_title = getattr(rule.source_module, "title", "the source module")
        condition_labels = {
            ModuleBranchRule.CONDITION_SUCCESS: f"{source_title} is answered correctly",
            ModuleBranchRule.CONDITION_FAILURE: f"{source_title} is answered incorrectly",
            ModuleBranchRule.CONDITION_COMPLETED: f"{source_title} is completed",
            ModuleBranchRule.CONDITION_SCORE_GTE: f"{source_title} score is at least {rule.threshold or 70:g}%",
            ModuleBranchRule.CONDITION_SCORE_LT: f"{source_title} score is below {rule.threshold or 70:g}%",
        }
        return condition_labels.get(rule.condition_type, f"{source_title} meets its branch condition")

    if len(rules) == 1:
        return f"Unlocks when {describe(rules[0])}"
    return "Unlocks when " + " or ".join(describe(rule) for rule in rules)
