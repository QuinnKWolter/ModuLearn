from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import Max


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
    rows = [
        ModuleProgress(user=enrollment.student, module=module, enrollment=enrollment)
        for enrollment in enrollments
        if enrollment.id not in existing
    ]
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
    return AccessState(True, False, _rule_reason(unit.unlock_rule) or "Locked until the instructor conditions are met")


def evaluate_module_access(module, enrollment, *, unit_state: AccessState | None = None, include_hidden: bool = False) -> AccessState:
    if not module.is_visible and not include_hidden:
        return AccessState(False, False, "Hidden by instructor")
    if unit_state is not None and not unit_state.can_access:
        return AccessState(unit_state.is_visible, False, unit_state.reason or "Unit is locked")
    if not module.is_locked:
        return AccessState(True, True)
    if _rule_passes(module.unlock_rule, enrollment, subject_module=module):
        return AccessState(True, True)
    return AccessState(True, False, _rule_reason(module.unlock_rule) or "Locked until the instructor conditions are met")


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
    if condition_type == "previous_unit_accessed":
        unit = subject_unit or getattr(subject_module, "unit", None)
        previous_unit = _previous_unit(unit)
        return _unit_accessed(enrollment, previous_unit.id) if previous_unit else True
    if condition_type == "previous_unit_completed":
        unit = subject_unit or getattr(subject_module, "unit", None)
        previous_unit = _previous_unit(unit)
        return _unit_completed(enrollment, previous_unit.id) if previous_unit else True

    return False


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


def _rule_reason(rule: dict[str, Any] | None) -> str:
    labels = {
        "module_accessed": "Unlocks after the selected module is accessed",
        "resource_accessed": "Unlocks after the selected resource is accessed",
        "module_completed": "Unlocks after the selected module is completed",
        "form_completed": "Unlocks after the selected form is completed",
        "survey_completed": "Unlocks after the selected survey is completed",
        "quiz_completed": "Unlocks after the selected quiz is completed",
        "unit_accessed": "Unlocks after the selected unit has been fully accessed",
        "unit_completed": "Unlocks after the selected unit is completed",
        "previous_unit_accessed": "Unlocks after the previous unit has been fully accessed",
        "previous_unit_completed": "Unlocks after the previous unit is completed",
    }
    conditions = (rule or {}).get("conditions") or []
    if not conditions:
        return ""
    return labels.get(conditions[0].get("type"), "")
