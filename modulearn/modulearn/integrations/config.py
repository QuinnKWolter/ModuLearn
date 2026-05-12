from __future__ import annotations

import os
from urllib.parse import urljoin

from django.conf import settings


def get_script_name() -> str:
    script_name = getattr(settings, "FORCE_SCRIPT_NAME", "") or ""
    return script_name.rstrip("/")


def prefixed_path(path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    script_name = get_script_name()
    if not script_name:
        return normalized_path
    return f"{script_name}{normalized_path}"


def get_course_authoring_base_url() -> str:
    return os.getenv(
        "COURSE_AUTHORING_BASE_URL",
        "https://proxy.personalized-learning.org/next.course-authoring",
    ).rstrip("/")


def build_course_authoring_url(path: str) -> str:
    path = path.lstrip("/")
    return urljoin(f"{get_course_authoring_base_url()}/", path)


def get_knowledge_tree_base_url() -> str:
    return getattr(settings, "KNOWLEDGETREE", {}).get("API_URL", "http://adapt2.sis.pitt.edu").rstrip("/")
