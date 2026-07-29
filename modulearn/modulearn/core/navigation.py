from django.urls import reverse
from django.utils.translation import gettext as _

from .roles import get_user_role_snapshot


def _nav_item(key, label, url, *, section="primary", requires_auth=False, requires_guest=False, match_prefix=False):
    return {
        "key": key,
        "label": label,
        "display_label": _(label),
        "url": url,
        "section": section,
        "requires_auth": requires_auth,
        "requires_guest": requires_guest,
        "match_prefix": match_prefix,
    }


def build_navigation(request):
    user = getattr(request, "user", None)
    is_authenticated = bool(user and user.is_authenticated)
    current_path = getattr(request, "path", "") or ""
    role_snapshot = get_user_role_snapshot(user)

    items = [
        _nav_item("home", "Home", reverse("main:home")),
        _nav_item("student", "Student", reverse("dashboard:student_dashboard"), requires_auth=True),
        _nav_item("instructor", "Instructor", reverse("dashboard:instructor_dashboard"), requires_auth=True),
        _nav_item("analytics", "Analytics", reverse("dashboard:modulearn_analytics_dashboard"), requires_auth=True, match_prefix=True),
        _nav_item("profile", "Profile", reverse("accounts:profile"), requires_auth=True, match_prefix=True),
        _nav_item("login", "Login", reverse("accounts:login"), requires_guest=True),
        _nav_item("signup", "Sign Up", reverse("accounts:signup"), requires_guest=True),
        _nav_item("info", "Info", reverse("main:info"), match_prefix=True),
    ]

    if not is_authenticated:
        visible = [item for item in items if not item["requires_auth"] and (not item["requires_guest"] or not is_authenticated)]
        for item in visible:
            item["is_active"] = (
                current_path == item["url"] or
                (item["match_prefix"] and item["url"] != "/" and current_path.startswith(item["url"]))
            )
        return visible

    if getattr(user, "is_anonymous_participant", False):
        return []

    filtered = []
    for item in items:
        if item["requires_guest"]:
            continue
        if item["key"] == "student" and not role_snapshot["effective_is_student"]:
            continue
        if item["key"] in {"instructor", "analytics"} and not role_snapshot["effective_is_instructor"]:
            continue
        item["is_active"] = (
            current_path == item["url"] or
            (item["match_prefix"] and item["url"] != "/" and current_path.startswith(item["url"]))
        )
        filtered.append(item)
    return filtered
