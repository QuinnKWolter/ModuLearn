from __future__ import annotations

from django.db import transaction

from modulearn.learning.services.course_plugins import is_course_plugin_enabled


PLUGIN_KEY = "adaptive_branching"


def has_dynamic_module_unlock(enrollment, module) -> bool:
    if not enrollment or not module or not getattr(module, "unit_id", None):
        return False
    course = module.unit.course
    if not is_course_plugin_enabled(course, PLUGIN_KEY):
        return False

    from courses.models import EnrollmentModuleUnlock

    return EnrollmentModuleUnlock.objects.filter(
        enrollment=enrollment,
        module=module,
        source_rule__active=True,
    ).exists()


def handle_progress_event(event) -> list:
    if not event or event.event_type not in {"progress", "outcome", "completion"}:
        return []

    module_progress = event.module_progress
    enrollment = module_progress.enrollment
    source_module = module_progress.module
    course = getattr(source_module, "course", None)
    if not enrollment or not course or not is_course_plugin_enabled(course, PLUGIN_KEY):
        return []

    from courses.models import EnrollmentModuleUnlock, ModuleBranchRule

    rules = (
        ModuleBranchRule.objects.filter(
            course=course,
            source_module=source_module,
            active=True,
        )
        .select_related("target_module")
        .order_by("priority", "id")
    )
    created_unlocks = []
    with transaction.atomic():
        for rule in rules:
            if not _rule_matches(rule, event, module_progress):
                continue

            unlock, created = EnrollmentModuleUnlock.objects.get_or_create(
                enrollment=enrollment,
                module=rule.target_module,
                source_rule=rule,
                defaults={
                    "source_module": source_module,
                    "reason": rule.condition_type,
                },
            )
            if created:
                created_unlocks.append(unlock)
    return created_unlocks


def _rule_matches(rule, event, module_progress) -> bool:
    condition_type = rule.condition_type
    score = event.score if event.score is not None else module_progress.score
    success = bool(event.success)

    if condition_type == "success":
        return success
    if condition_type == "failure":
        return not success and score is not None
    if condition_type == "completed":
        return bool(module_progress.is_complete) or event.progress >= 1.0
    if condition_type == "score_gte":
        return score is not None and score >= _threshold(rule, 70.0)
    if condition_type == "score_lt":
        return score is not None and score < _threshold(rule, 70.0)
    return False


def _threshold(rule, default: float) -> float:
    return float(rule.threshold if rule.threshold is not None else default)
