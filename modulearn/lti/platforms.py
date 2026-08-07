"""Helpers for inbound LMS platform registration and LTI 1.3 setup."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse
from pylti1p3.tool_config import ToolConfDict

from .models import LTIPlatformRegistration


def normalize_platform_issuer(value: str) -> str:
    """Normalize an LMS issuer value for lookup while preserving path segments."""
    issuer = str(value or "").strip()
    return issuer.rstrip("/") if issuer else ""


def _resolve_key_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return settings.BASE_DIR / path


def _read_key_file(path_value: str) -> str:
    return _resolve_key_path(path_value).read_text(encoding="utf-8")


def _tool_key_paths(config_item: dict) -> tuple[str, str]:
    public_key_file = (
        config_item.get("public_key_file")
        or getattr(settings, "LTI_PUBLIC_KEY_FILE", "./modulearn/public.key")
    )
    private_key_file = (
        config_item.get("private_key_file")
        or getattr(settings, "LTI_PRIVATE_KEY_FILE", "./modulearn/private.key")
    )
    return public_key_file, private_key_file


def get_lti13_config_dict() -> dict:
    """Merge settings-backed LTI 1.3 config with database platform registrations."""
    config = {
        normalize_platform_issuer(issuer): conf
        for issuer, conf in deepcopy(getattr(settings, "LTI_CONFIG", {})).items()
    }

    for registration in LTIPlatformRegistration.objects.filter(is_active=True):
        issuer_config = registration.to_tool_conf()
        issuer = normalize_platform_issuer(registration.issuer)
        existing = config.get(issuer)
        if existing is None:
            config[issuer] = [issuer_config]
        elif isinstance(existing, list):
            existing.append(issuer_config)
        else:
            existing["default"] = True
            config[issuer] = [existing, issuer_config]

    return config


def build_lti13_tool_conf() -> ToolConfDict:
    """Build a pylti1p3 ToolConfDict and attach the local tool keys."""
    config = get_lti13_config_dict()
    tool_conf = ToolConfDict(config)

    for issuer, issuer_config in config.items():
        items = issuer_config if isinstance(issuer_config, list) else [issuer_config]
        for item in items:
            client_id = item.get("client_id")
            public_key_file, private_key_file = _tool_key_paths(item)
            public_key = _read_key_file(public_key_file)
            private_key = _read_key_file(private_key_file)
            if tool_conf.check_iss_has_many_clients(issuer):
                tool_conf.set_public_key(issuer, public_key, client_id=client_id)
                tool_conf.set_private_key(issuer, private_key, client_id=client_id)
            else:
                tool_conf.set_public_key(issuer, public_key)
                tool_conf.set_private_key(issuer, private_key)

    return tool_conf


def build_absolute_url(request, path: str, query: dict | None = None) -> str:
    url = request.build_absolute_uri(path)
    if query:
        clean_query = {key: value for key, value in query.items() if value not in (None, "")}
        if clean_query:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urlencode(clean_query)}"
    return url


def lti_setup_payload(request, course_instance_id=None) -> dict:
    """Return copyable LTI 1.1 and 1.3 setup details for a course session."""
    course_query = {"course_id": course_instance_id} if course_instance_id else None
    course_custom_parameters = (
        f"course_id={course_instance_id}\nmodulearn_course_id={course_instance_id}"
        if course_instance_id
        else ""
    )
    launch_path = reverse("lti:launch")
    login_path = reverse("lti:login")
    jwks_path = reverse("lti:jwks")
    config_path = reverse("lti:config")
    tool_config = getattr(settings, "LTI_TOOL_CONFIG", {})

    return {
        "course_instance_id": course_instance_id,
        "tool": {
            "name": tool_config.get("title") or "ModuLearn",
            "description": tool_config.get("description") or "ModuLearn course session launch",
            "privacy": "public",
            "default_launch_container": "Embed, without blocks",
            "deep_linking_supported": False,
        },
        "lti_11": {
            "launch_url": build_absolute_url(request, launch_path, course_query),
            "cartridge_xml_url": build_absolute_url(request, config_path, course_query),
            "consumer_key": getattr(settings, "LTI_11_CONSUMER_KEY", ""),
            "shared_secret": getattr(settings, "LTI_11_CONSUMER_SECRET", ""),
            "custom_parameters": course_custom_parameters,
        },
        "lti_13": {
            "tool_url": build_absolute_url(request, launch_path, course_query),
            "target_link_uri": build_absolute_url(request, launch_path, course_query),
            "redirect_uri": build_absolute_url(request, launch_path),
            "initiate_login_url": build_absolute_url(request, login_path),
            "oidc_login_url": build_absolute_url(request, login_path),
            "jwks_url": build_absolute_url(request, jwks_path),
            "public_keyset_url": build_absolute_url(request, jwks_path),
            "custom_parameters": course_custom_parameters,
        },
    }
