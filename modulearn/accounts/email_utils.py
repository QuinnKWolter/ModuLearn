from __future__ import annotations

import logging

from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


def normalize_email_address(value: str | None) -> str:
    """Return the canonical representation used for stored email identities."""
    return (value or "").strip().casefold()


def emails_equal(left: str | None, right: str | None) -> bool:
    left_normalized = normalize_email_address(left)
    return bool(left_normalized and left_normalized == normalize_email_address(right))


def find_user_by_email(value: str | None):
    email = normalize_email_address(value)
    if not email:
        return None

    User = get_user_model()
    matches = list(User.objects.filter(email__iexact=email).order_by("id")[:2])
    if len(matches) > 1:
        logger.warning(
            "Multiple users share the case-insensitive email identity %s; using user id %s",
            email,
            matches[0].id,
        )
    return matches[0] if matches else None


def unique_username_for_email(value: str, *, local_part_only: bool = False) -> str:
    User = get_user_model()
    email = normalize_email_address(value)
    base = email.split("@", 1)[0] if local_part_only else email
    base = (base or "student")[:150]
    candidate = base
    counter = 1
    while User.objects.filter(username__iexact=candidate).exists():
        suffix = str(counter)
        candidate = f"{base[:150 - len(suffix)]}{suffix}"
        counter += 1
    return candidate
