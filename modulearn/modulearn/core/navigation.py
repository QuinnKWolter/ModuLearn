from django.urls import reverse

from .roles import get_user_role_snapshot


def _nav_item(label, url, *, section="primary", requires_auth=False, requires_guest=False, match_prefix=False):
    return {
        "label": label,
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
        _nav_item("Home", reverse("main:home")),
        _nav_item("Student", reverse("dashboard:student_dashboard"), requires_auth=True),
        _nav_item("Instructor", reverse("dashboard:instructor_dashboard"), requires_auth=True),
        _nav_item("Analytics", reverse("dashboard:modulearn_analytics_dashboard"), requires_auth=True, match_prefix=True),
        _nav_item("Legacy", reverse("dashboard:legacy_dashboard"), section="secondary", requires_auth=True, match_prefix=True),
        _nav_item("Profile", reverse("accounts:profile"), requires_auth=True, match_prefix=True),
        _nav_item("Login", reverse("accounts:login"), requires_guest=True),
        _nav_item("Sign Up", reverse("accounts:signup"), requires_guest=True),
        _nav_item("About", reverse("main:about"), match_prefix=True),
        _nav_item("Contact", reverse("main:contact"), match_prefix=True),
    ]

    if not is_authenticated:
        visible = [item for item in items if not item["requires_auth"] and (not item["requires_guest"] or not is_authenticated)]
        for item in visible:
            item["is_active"] = (
                current_path == item["url"] or
                (item["match_prefix"] and item["url"] != "/" and current_path.startswith(item["url"]))
            )
        return visible

    filtered = []
    for item in items:
        if item["requires_guest"]:
            continue
        if item["label"] == "Student" and not role_snapshot["effective_is_student"]:
            continue
        if item["label"] in {"Instructor", "Analytics", "Legacy"} and not role_snapshot["effective_is_instructor"]:
            continue
        item["is_active"] = (
            current_path == item["url"] or
            (item["match_prefix"] and item["url"] != "/" and current_path.startswith(item["url"]))
        )
        filtered.append(item)
    return filtered
