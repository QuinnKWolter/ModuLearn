"""Redact authentication material after formatting, including exception text."""
import logging
import re
import time
from contextvars import ContextVar

request_id_context = ContextVar('request_id', default='-')


_KEYS = r'(?:sid|sessionid|jsessionid|csrftoken|csrfmiddlewaretoken|pwd|password|course_authoring_password|token|access_token|refresh_token|oauth_signature)'
_PLAIN = re.compile(r"(?i)(\b" + _KEYS + r"(?:=|['\"]?\s*:\s*(?:\[\s*)?['\"]?))([^&\s'\"<>,;)\]}]+)")
_ENCODED = re.compile(r'(?i)((?:\b|%3F|%26)' + _KEYS + r'%3D).*?(?=%26|[\s\'"<>]|$)')


def redact_credentials(value):
    value = _ENCODED.sub(lambda match: match.group(1) + '[redacted]', str(value))
    return _PLAIN.sub(lambda match: match.group(1) + '[redacted]', value)


class RedactingFormatter(logging.Formatter):
    converter = time.gmtime

    def format(self, record):
        record.request_id = request_id_context.get()
        return redact_credentials(super().format(record))
