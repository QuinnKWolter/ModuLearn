from __future__ import annotations

from .config import build_course_authoring_url


def build_course_export_url(course_id: str) -> str:
    return build_course_authoring_url(f"api/courses/{course_id}/export")


def build_x_login_token_url() -> str:
    return build_course_authoring_url("api/auth/x-login-token")


def build_x_login_url() -> str:
    return build_course_authoring_url("api/auth/x-login")


def build_course_authoring_app_url() -> str:
    return f"{build_course_authoring_url('')}/#/modulearn"
