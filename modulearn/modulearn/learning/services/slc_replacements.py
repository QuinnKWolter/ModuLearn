from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings

from courses.models import Module


@dataclass(frozen=True)
class SLCReplacement:
    original_url: str
    replacement_url: str
    selected_protocol: str
    supported_protocols: list[str]
    module_type: str
    metadata: dict


def apply_slc_legacy_replacement(
    content_url: str | None,
    *,
    current_module_type: str | None = None,
    current_supported_protocols: list[str] | None = None,
) -> SLCReplacement | None:
    """Return replacement details when a legacy SLC URL has a modern equivalent."""
    original_url = (content_url or "").strip()
    if not original_url:
        return None

    mapping = _find_mapping(original_url)
    if not mapping:
        return None

    replacement_url, selected_protocol = _best_replacement_url(mapping)
    if not replacement_url:
        return None

    supported_protocols = _supported_protocols(mapping, selected_protocol)
    module_type = (
        Module.MODULE_TYPE_SPLICE_SMART_CONTENT
        if selected_protocol == "splice"
        else (current_module_type or Module.MODULE_TYPE_EXTERNAL_LINK)
    )
    if selected_protocol and selected_protocol not in supported_protocols:
        supported_protocols.insert(0, selected_protocol)

    return SLCReplacement(
        original_url=original_url,
        replacement_url=replacement_url,
        selected_protocol=selected_protocol,
        supported_protocols=supported_protocols or (current_supported_protocols or []),
        module_type=module_type,
        metadata={
            "replaced": True,
            "original_url": original_url,
            "old_item_id": mapping.get("old_item_id") or "",
            "old_title": mapping.get("old_title") or "",
            "replacement_item_id": mapping.get("replacement_item_id") or "",
            "replacement_title": mapping.get("replacement_title") or "",
            "selected_protocol": selected_protocol,
            "match_confidence": mapping.get("match_confidence") or "",
            "prompt_similarity": mapping.get("prompt_similarity"),
            "fallback_urls": mapping.get("fallback_urls") or {},
        },
    )


def apply_replacement_metadata(content_data: dict | None, replacement: SLCReplacement | None) -> dict | None:
    if not replacement:
        return content_data
    next_data = dict(content_data or {})
    next_data["slc_legacy_replacement"] = replacement.metadata
    return next_data


def _find_mapping(url: str) -> dict | None:
    mappings = _load_url_mappings()
    for candidate in _lookup_candidates(url):
        mapping = mappings.get(candidate)
        if mapping:
            return mapping
    return None


def _best_replacement_url(mapping: dict) -> tuple[str, str]:
    splice_url = mapping.get("replacement_splice_url") or ""
    if splice_url:
        return splice_url, "splice"

    fallback_urls = mapping.get("fallback_urls") or {}
    for protocol in ("HTML", "LTI", "PITT"):
        fallback_url = fallback_urls.get(protocol)
        if fallback_url:
            return fallback_url, protocol.lower()
    return "", ""


def _supported_protocols(mapping: dict, selected_protocol: str) -> list[str]:
    protocols = []
    if selected_protocol:
        protocols.append(selected_protocol)
    for protocol in (mapping.get("fallback_urls") or {}).keys():
        normalized = str(protocol or "").strip().lower()
        if normalized and normalized not in protocols:
            protocols.append(normalized)
    return protocols


def _lookup_candidates(url: str) -> list[str]:
    candidates = []

    def add(value: str):
        value = value.strip()
        if value and value not in candidates:
            candidates.append(value)

    add(url)
    canonical = _canonical_url(url)
    add(canonical)

    parsed = urlsplit(canonical or url)
    if parsed.scheme in {"http", "https"}:
        alternate_scheme = "https" if parsed.scheme == "http" else "http"
        add(urlunsplit((alternate_scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment)))
    return candidates


def _canonical_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip()
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    query = urlencode(sorted(query_pairs), doseq=True)
    return urlunsplit((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path,
        query,
        "",
    ))


@lru_cache(maxsize=1)
def _load_url_mappings() -> dict:
    path = Path(settings.BASE_DIR) / "data" / "slc_legacy_url_replacements.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    raw_mappings = data.get("urls") if isinstance(data, dict) else {}
    mappings = {}
    for url, mapping in (raw_mappings or {}).items():
        if not isinstance(mapping, dict):
            continue
        for candidate in _lookup_candidates(str(url)):
            mappings[candidate] = mapping
    return mappings
