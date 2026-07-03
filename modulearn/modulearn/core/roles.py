from __future__ import annotations

from courses.models import Enrollment
from dashboard.kt_utils import (
    get_course_ids_from_aggregate_db,
    get_user_groups_with_course_ids,
    get_user_groups_with_masterygrids_nodes,
)


def _looks_like_group_login(value: str) -> bool:
    value = (value or "").strip()
    if not value:
        return False
    return (" " not in value) and ("," not in value)


def _build_legacy_group_fallback(user, *, include_node_ids=False):
    groups = []
    for group in getattr(user, "kt_groups", []) or []:
        if isinstance(group, dict):
            group_name = (
                group.get("group_name")
                or group.get("name")
                or group.get("title")
                or group.get("group_login")
                or ""
            )
            group_login = group.get("group_login") or group.get("login") or ""
            if not group_login and _looks_like_group_login(group_name):
                group_login = group_name
            course_ids = [str(course_id) for course_id in (group.get("course_ids") or []) if course_id]
        else:
            group_name = str(group)
            group_login = group_name if _looks_like_group_login(group_name) else ""
            course_ids = []

        payload = {
            "group_name": group_name,
            "group_login": group_login,
            "course_ids": course_ids,
            "is_actionable": bool(group_login),
        }
        if include_node_ids:
            payload["node_id"] = None
        groups.append(payload)

    actionable_group_logins = [group["group_login"] for group in groups if group["group_login"]]
    if actionable_group_logins:
        try:
            course_id_mappings = get_course_ids_from_aggregate_db(actionable_group_logins)
        except Exception:
            course_id_mappings = {}

        for group in groups:
            if group["group_login"] and not group["course_ids"]:
                group["course_ids"] = course_id_mappings.get(group["group_login"], [])
    return groups


def get_legacy_course_groups(user):
    if hasattr(user, "_modulearn_legacy_course_groups"):
        return user._modulearn_legacy_course_groups

    groups = []
    if getattr(user, "is_authenticated", False):
        if user.kt_login or user.kt_user_id:
            try:
                groups = get_user_groups_with_course_ids(user)
            except Exception:
                groups = []

        if not groups and getattr(user, "kt_groups", None):
            groups = _build_legacy_group_fallback(user)

    user._modulearn_legacy_course_groups = groups
    return groups


def get_legacy_masterygrids_groups(user):
    if hasattr(user, "_modulearn_legacy_masterygrids_groups"):
        return user._modulearn_legacy_masterygrids_groups

    groups = []
    if getattr(user, "is_authenticated", False):
        if user.kt_login or user.kt_user_id:
            try:
                groups = get_user_groups_with_masterygrids_nodes(user)
            except Exception:
                groups = []
            if not groups:
                try:
                    groups = get_user_groups_with_course_ids(user)
                    for group in groups:
                        group.setdefault("masterygrids_node_id", None)
                except Exception:
                    groups = []

        if not groups and getattr(user, "kt_groups", None):
            groups = _build_legacy_group_fallback(user, include_node_ids=True)

    user._modulearn_legacy_masterygrids_groups = groups
    return groups


def get_user_role_snapshot(user, *, include_legacy_groups=False):
    if hasattr(user, "_modulearn_role_snapshot"):
        cached_snapshot = user._modulearn_role_snapshot
        if not include_legacy_groups or cached_snapshot.get("_includes_legacy_groups"):
            return cached_snapshot

    snapshot = {
        "effective_is_student": False,
        "effective_is_instructor": False,
        "primary_role": None,
        "legacy_course_groups": [],
        "_includes_legacy_groups": False,
    }

    if not getattr(user, "is_authenticated", False):
        if not include_legacy_groups:
            user._modulearn_role_snapshot = snapshot
        return snapshot

    native_instructor = bool(getattr(user, "is_instructor", False))
    native_student = bool(getattr(user, "is_student", False))
    enrolled_student = Enrollment.objects.filter(student=user, active=True).exists()
    legacy_course_groups = get_legacy_course_groups(user) if include_legacy_groups and native_instructor else []
    effective_is_instructor = native_instructor
    effective_is_student = (native_student or enrolled_student) and not effective_is_instructor

    snapshot = {
        "effective_is_student": effective_is_student,
        "effective_is_instructor": effective_is_instructor,
        "primary_role": "instructor" if effective_is_instructor else "student" if effective_is_student else None,
        "legacy_course_groups": legacy_course_groups,
        "_includes_legacy_groups": include_legacy_groups,
    }

    if not include_legacy_groups:
        user._modulearn_role_snapshot = snapshot
    return snapshot
