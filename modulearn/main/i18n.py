"""Cached, local interface catalogs shared by Python, templates and JavaScript.

English messages are stable keys. Interpolate authored content only after lookup.
The browser receives one catalog, and English needs no browser catalog at all.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from django.utils.translation import get_language


@lru_cache(maxsize=8)
def catalog(language):
    if not re.fullmatch(r'[a-z]{2,3}(?:-[a-z0-9]+)*', language):
        return {}
    messages = {}
    for path in sorted((Path(__file__).parent / 'locales' / language).glob('*.json')):
        messages.update(json.loads(path.read_text(encoding='utf-8')))
    return messages


def translate(message, **parameters):
    message = str(message)
    translated = catalog(get_language() or 'en').get(message, message)
    # A single substitution prevents values containing {tokens} from being
    # interpreted again as another parameter.
    return re.sub(r'\{(\w+)\}', lambda match: str(parameters.get(match[1], match[0])), translated)
