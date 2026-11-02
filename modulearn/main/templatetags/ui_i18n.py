"""Shared feature messages for templates and interactive UI; English is fallback."""
from django import template
from django.utils.translation import get_language
from django.utils.html import json_script
from django.conf import settings
from main.i18n import catalog, translate

register = template.Library()

@register.simple_tag
@register.filter(name='ui_text')
def ui(message, **parameters):
    return translate(message, **parameters)


@register.simple_tag
def ui_count(singular, plural, count):
    # Each language translates the whole count phrase (Serbian uses neutral
    # labels), rather than appending an English "s" to a translated noun.
    source = singular if count == 1 else plural
    return translate('{count} ' + source, count=count)

@register.simple_tag
def ui_catalog():
    language = get_language() or 'en'
    # English source strings are already in the page/scripts; don't ship them twice.
    return json_script(catalog(language) if language != 'en' else {}, 'modulearn-ui-messages')


@register.simple_tag(takes_context=True)
def ui_languages(context):
    return [{'code': code, 'name': name, 'active': code == (get_language() or 'en')}
            for code, name in settings.LANGUAGES]


@register.simple_tag(takes_context=True)
def ui_return_path(context):
    request = context['request']
    query = request.GET.copy()
    query.pop('lang', None)
    return request.path + ('?' + query.urlencode() if query else '')
