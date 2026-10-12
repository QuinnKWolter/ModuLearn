"""Shared feature messages for templates and interactive UI; English is fallback."""
import json
import re
from functools import lru_cache
from pathlib import Path
from django import template
from django.utils.translation import get_language
from django.utils.html import json_script

register = template.Library()

@lru_cache(maxsize=8)
def catalog(language):
    if not re.fullmatch(r'[a-z]{2,3}(?:-[a-z0-9]+)*', language):
        return {}
    messages = {}
    for path in sorted((Path(__file__).parents[1] / 'locales' / language).glob('*.json')):
        messages.update(json.loads(path.read_text(encoding='utf-8')))
    return messages

@register.simple_tag
def ui(message, **parameters):
    translated = catalog((get_language() or 'en').split('-')[0]).get(message, message)
    for key, value in parameters.items():
        translated = translated.replace('{' + key + '}', str(value))
    return translated

@register.simple_tag
def ui_catalog():
    return json_script(catalog((get_language() or 'en').split('-')[0]), 'modulearn-ui-messages')
