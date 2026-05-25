from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import urlencode

import requests


class SonaCreditError(Exception):
    pass


def client_credit_url(source, survey_code: str) -> str:
    base_url = (source.sona_base_url or "").rstrip("/")
    params = {
        "experiment_id": source.sona_experiment_id,
        "credit_token": source.sona_credit_token,
        "survey_code": survey_code,
    }
    return f"{base_url}/webstudy_credit.aspx?{urlencode(params)}"


def grant_credit_server_side(source, survey_code: str) -> dict:
    base_url = (source.sona_base_url or "").rstrip("/")
    if not base_url or not source.sona_experiment_id or not source.sona_credit_token:
        raise SonaCreditError("SONA server-side credit is not fully configured.")

    response = requests.get(
        f"{base_url}/services/SonaAPI.svc/WebstudyCredit",
        params={
            "experiment_id": source.sona_experiment_id,
            "credit_token": source.sona_credit_token,
            "survey_code": survey_code,
        },
        timeout=10,
    )
    metadata = {
        "http_status": response.status_code,
        "body": response.text[:1000],
    }
    if response.status_code >= 400:
        raise SonaCreditError(f"SONA credit request failed with HTTP {response.status_code}.")

    try:
        root = ET.fromstring(response.content)
        metadata["xml_root"] = root.tag
        metadata["xml_text"] = " ".join(text.strip() for text in root.itertext() if text.strip())[:1000]
    except ET.ParseError:
        metadata["xml_parse_error"] = True

    body_lower = response.text.lower()
    if "error" in body_lower or "fail" in body_lower:
        raise SonaCreditError("SONA returned an error response while granting credit.")
    return metadata
