from __future__ import annotations

from dataclasses import dataclass
import re

import requests
from django.conf import settings
from django.core.cache import cache

PROLIFIC_COMPLETION_BASE_URL = "https://app.prolific.com/submissions/complete"
PROLIFIC_JWKS_URL = "https://api.prolific.com/api/v1/.well-known/jwks.json"


class ProlificVerificationError(Exception):
    pass


@dataclass(frozen=True)
class ProlificIds:
    pid: str
    study_id: str = ""
    session_id: str = ""


PROLIFIC_ID_PATTERN = re.compile(r"^[a-fA-F0-9]{24}$")


def completion_url(code: str) -> str:
    return f"{PROLIFIC_COMPLETION_BASE_URL}?cc={code}"


def validate_prolific_ids(ids: ProlificIds):
    missing = []
    if not ids.pid:
        missing.append("PROLIFIC_PID")
    if not ids.study_id:
        missing.append("STUDY_ID")
    if not ids.session_id:
        missing.append("SESSION_ID")
    if missing:
        raise ProlificVerificationError(f"Missing Prolific parameter: {', '.join(missing)}.")

    invalid = []
    if not PROLIFIC_ID_PATTERN.match(ids.pid):
        invalid.append("PROLIFIC_PID")
    if not PROLIFIC_ID_PATTERN.match(ids.study_id):
        invalid.append("STUDY_ID")
    if not PROLIFIC_ID_PATTERN.match(ids.session_id):
        invalid.append("SESSION_ID")
    if invalid:
        raise ProlificVerificationError(f"Invalid Prolific identifier format: {', '.join(invalid)}.")


def verify_secured_url(token: str, expected: ProlificIds) -> dict:
    if not token:
        raise ProlificVerificationError("Missing Prolific secured URL token.")
    try:
        import jwt
        from jwt import PyJWKClient
    except Exception as exc:  # pragma: no cover - depends on optional runtime package
        raise ProlificVerificationError("PyJWT is required for Prolific secured URL verification.") from exc

    jwks_url = getattr(settings, "PROLIFIC_JWKS_URL", PROLIFIC_JWKS_URL)
    cache_key = "recruitment:prolific:jwks_client"
    jwks_client = cache.get(cache_key)
    if jwks_client is None:
        jwks_client = PyJWKClient(jwks_url)
        cache.set(cache_key, jwks_client, 60 * 60 * 4)

    signing_key = jwks_client.get_signing_key_from_jwt(token)
    try:
        claims = jwt.decode(token, signing_key.key, algorithms=["RS256"], options={"verify_aud": False})
    except Exception as exc:
        cache.delete(cache_key)
        raise ProlificVerificationError("Invalid Prolific secured URL token.") from exc

    _assert_claim_match(claims, "PROLIFIC_PID", expected.pid)
    if expected.study_id:
        _assert_claim_match(claims, "STUDY_ID", expected.study_id)
    if expected.session_id:
        _assert_claim_match(claims, "SESSION_ID", expected.session_id)
    return claims


def verify_submission_api(expected: ProlificIds) -> dict:
    token = getattr(settings, "PROLIFIC_API_TOKEN", "")
    if not token or not expected.session_id:
        return {"verified": False, "reason": "submission_api_not_configured"}

    base_url = getattr(settings, "PROLIFIC_API_BASE_URL", "https://api.prolific.com/api/v1")
    response = requests.get(
        f"{base_url.rstrip('/')}/submissions/{expected.session_id}/",
        headers={"Authorization": f"Token {token}"},
        timeout=8,
    )
    if response.status_code >= 400:
        raise ProlificVerificationError(f"Prolific submission verification failed with HTTP {response.status_code}.")
    payload = response.json()
    values = payload.get("data", payload)
    participant_id = str(values.get("participant_id") or values.get("PROLIFIC_PID") or values.get("participant") or "")
    study_id = str(values.get("study_id") or values.get("STUDY_ID") or values.get("study") or "")
    if participant_id and participant_id != expected.pid:
        raise ProlificVerificationError("Prolific participant id did not match the submission.")
    if expected.study_id and study_id and study_id != expected.study_id:
        raise ProlificVerificationError("Prolific study id did not match the submission.")
    return {"verified": True, "payload": payload}


def _assert_claim_match(claims: dict, key: str, expected: str):
    value = claims.get(key) or claims.get(key.lower())
    if expected and value and str(value) != str(expected):
        raise ProlificVerificationError(f"Prolific token claim {key} did not match the URL parameter.")
