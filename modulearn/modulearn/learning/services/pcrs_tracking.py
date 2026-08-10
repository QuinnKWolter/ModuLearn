from __future__ import annotations

import json
import logging
from urllib.parse import parse_qs, urlparse

from django.http import HttpResponse, QueryDict

logger = logging.getLogger(__name__)

PCRS_HOST = "pcrs.utm.utoronto.ca"


def is_pcrs_url(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    return parsed.hostname == PCRS_HOST and parsed.path.startswith("/mgrids/")


def is_pcrs_run_path(host: str, path_rest: str) -> bool:
    path = "/" + (path_rest or "").lstrip("/")
    return host == PCRS_HOST and path.startswith("/mgrids/problems/") and path.endswith("/run")


def capture_pcrs_result_if_possible(request, host: str, path_rest: str, response: HttpResponse):
    if request.method != "POST" or not is_pcrs_run_path(host, path_rest):
        return
    if getattr(response, "status_code", 500) >= 400:
        return

    try:
        payload = json.loads((response.content or b"{}").decode("utf-8"))
    except (TypeError, ValueError, UnicodeDecodeError):
        logger.warning("[PCRS Tracking] Could not parse run response as JSON")
        return
    if not isinstance(payload, dict):
        return

    try:
        score = float(payload.get("score") or 0)
        max_score = float(payload.get("max_score") or 0)
    except (TypeError, ValueError):
        logger.warning("[PCRS Tracking] Invalid score payload: %s", payload)
        return
    if max_score <= 0:
        logger.warning("[PCRS Tracking] Missing max_score in response")
        return

    params = _referer_query_params(request)
    course_id = _first_query_value(params, "cid")
    username = _first_query_value(params, "usr")
    group_name = _first_query_value(params, "grp")
    if not (course_id and username):
        logger.warning("[PCRS Tracking] Missing cid/usr in referer; cannot map local progress")
        return

    try:
        from django.contrib.auth import get_user_model
        from courses.models import Course, CourseInstance, ModuleProgress
        from modulearn.learning.services.progress import apply_progress_snapshot, module_accepts_scored_attempt

        course = Course.objects.filter(id=course_id).first()
        user = get_user_model().objects.filter(username=username).first()
        if not course or not user:
            logger.warning("[PCRS Tracking] Could not find course/user for cid=%s usr=%s", course_id, username)
            return

        instance_qs = CourseInstance.objects.filter(course=course, enrollments__student=user)
        if group_name:
            instance_qs = instance_qs.filter(group_name=group_name)
        course_instance = instance_qs.order_by("-active", "-id").first()
        module = _find_pcrs_module(course, params, path_rest)
        if not course_instance or not module:
            logger.warning(
                "[PCRS Tracking] Could not map course session/module for cid=%s grp=%s module_id=%s sub=%s",
                course_id,
                group_name,
                _first_query_value(params, "module_id"),
                _first_query_value(params, "sub"),
            )
            return

        raw_progress = max(0.0, min(1.0, score / max_score))
        percent_score = raw_progress * 100.0

        module_progress, _ = ModuleProgress.get_or_create_progress(
            user=user,
            module=module,
            course_instance=course_instance,
        )
        if not module_accepts_scored_attempt(module_progress):
            logger.info(
                "[PCRS Tracking] Ignoring resubmission for single-attempt module user=%s module=%s",
                username,
                module.id,
            )
            return
        progress = max(raw_progress, module_progress.progress or 0.0)
        percent_score = max(percent_score, module_progress.score or 0.0)
        is_complete = bool(module_progress.is_complete or progress >= 1.0)

        apply_progress_snapshot(
            module_progress,
            source="pcrs",
            progress=progress,
            score=percent_score,
            success=bool(module_progress.success or raw_progress >= 1.0),
            is_complete=is_complete,
            payload={
                "pcrs_result": payload,
                "pcrs_submission": _submission_snapshot(request, params, path_rest),
                "score": score,
                "max_score": max_score,
                "progress_percent": percent_score,
            },
            event_type="completion" if is_complete and not module_progress.is_complete else "progress",
        )

        module_progress.attempts = (module_progress.attempts or 0) + 1
        module_progress.save(update_fields=["attempts", "last_accessed"])

        logger.info(
            "[PCRS Tracking] Recorded result for user=%s module=%s score=%s/%s progress=%.2f",
            username,
            module.id,
            score,
            max_score,
            progress,
        )
    except Exception:
        logger.exception("[PCRS Tracking] Failed to record local progress")


def _first_query_value(params: dict, key: str, default: str = "") -> str:
    value = params.get(key, default)
    if isinstance(value, list):
        return value[0] if value else default
    return value or default


def _query_values(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def _query_dict_payload(query_dict) -> dict:
    if not query_dict:
        return {}
    if hasattr(query_dict, "lists"):
        return {
            key: values[0] if len(values) == 1 else list(values)
            for key, values in query_dict.lists()
        }
    if isinstance(query_dict, dict):
        return {
            key: values[0] if isinstance(values, list) and len(values) == 1 else values
            for key, values in query_dict.items()
        }
    return {}


def _raw_body_text(request) -> str:
    try:
        body = request.body or b""
    except Exception:
        return ""
    if isinstance(body, str):
        return body
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("utf-8", errors="replace")


def _submission_snapshot(request, referer_params: dict, path_rest: str) -> dict:
    raw_body = _raw_body_text(request)
    form_payload = _query_dict_payload(getattr(request, "POST", None))
    if not form_payload and raw_body:
        form_payload = _query_dict_payload(QueryDict(raw_body, encoding="utf-8"))

    return {
        "path": getattr(request, "path", "") or request.META.get("PATH_INFO", ""),
        "path_rest": path_rest,
        "content_type": request.META.get("CONTENT_TYPE") or request.META.get("HTTP_CONTENT_TYPE", ""),
        "referer": request.META.get("HTTP_REFERER", ""),
        "referer_params": {
            key: values[0] if len(values) == 1 else values
            for key, values in ((key, _query_values(value)) for key, value in referer_params.items())
        },
        "form": form_payload,
        "raw_body": raw_body,
    }


def _referer_query_params(request) -> dict:
    referer = request.META.get("HTTP_REFERER", "")
    if not referer:
        return {}
    return parse_qs(urlparse(referer).query)


def _find_pcrs_module(course, params: dict, path_rest: str):
    from courses.models import Module

    module_id = _first_query_value(params, "module_id")
    if module_id:
        module = Module.objects.filter(id=module_id, unit__course=course).first()
        if module:
            return module

    sub = _first_query_value(params, "sub")
    act = _first_query_value(params, "act")
    path = "/" + (path_rest or "").lstrip("/")
    embed_path = path[:-4] + "embed" if path.endswith("/run") else ""

    for module in Module.objects.filter(unit__course=course).select_related("unit"):
        parsed = urlparse(module.content_url or "")
        module_params = parse_qs(parsed.query)
        if parsed.hostname != PCRS_HOST:
            continue
        if embed_path and parsed.path != embed_path:
            continue
        if sub and _first_query_value(module_params, "sub") != sub:
            continue
        if act and _first_query_value(module_params, "act") != act:
            continue
        return module
    return None
