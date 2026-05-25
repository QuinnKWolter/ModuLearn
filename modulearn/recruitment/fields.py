from __future__ import annotations

import base64
import hashlib

from django.conf import settings
from django.db import models

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover - optional runtime dependency guard
    Fernet = None
    InvalidToken = Exception


def _fernet():
    if Fernet is None:
        return None
    secret = str(settings.SECRET_KEY).encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


class EncryptedCharField(models.CharField):
    description = "CharField encrypted at rest with the project secret key when cryptography is available"

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, ""):
            return value
        value = str(value)
        if value.startswith("enc:"):
            return value
        fernet = _fernet()
        if fernet is None:
            return value
        token = fernet.encrypt(value.encode("utf-8")).decode("utf-8")
        return f"enc:{token}"

    def from_db_value(self, value, expression, connection):
        return self._decrypt(value)

    def to_python(self, value):
        value = super().to_python(value)
        return self._decrypt(value)

    def _decrypt(self, value):
        if value in (None, "") or not isinstance(value, str) or not value.startswith("enc:"):
            return value
        fernet = _fernet()
        if fernet is None:
            return value
        try:
            return fernet.decrypt(value[4:].encode("utf-8")).decode("utf-8")
        except InvalidToken:
            return value
