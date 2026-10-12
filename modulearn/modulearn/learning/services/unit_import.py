"""Strict additive unit packages; never route a partial unit through course import."""
import hashlib
import json
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.db.models import Max

from courses.models import Course, Module, Unit


def validate_unit_package(raw):
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError('Unit package must be under 10 MiB.')
    try:
        data = json.loads(raw.decode('utf-8-sig'))
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Expected UTF-8 JSON.') from exc
    if not isinstance(data, dict) or data.get('format') != 'modulearn.unit.v1' or data.get('ready') is not True:
        raise ValueError('Expected a verified modulearn.unit.v1 package with ready=true.')
    unit = data.get('unit')
    if not isinstance(unit, dict) or not isinstance(unit.get('title'), str) or not unit['title'].strip() or len(unit['title']) > 255:
        raise ValueError('A unit title of at most 255 characters is required.')
    entries = unit.get('modules')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 500:
        raise ValueError('Include between 1 and 500 modules.')
    result = []
    titles = set()
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            raise ValueError(f'Module {index}: expected an object.')
        title = entry.get('title', '')
        if not isinstance(title, str) or not title.strip() or len(title) > 255 or title.strip().casefold() in titles:
            raise ValueError(f'Module {index}: missing, duplicate or oversized title.')
        titles.add(title.strip().casefold())
        url = entry.get('content_url')
        try:
            URLValidator(schemes=['http', 'https'])(url)
            if urlsplit(url).username or urlsplit(url).password:
                raise ValueError('Credentials cannot be embedded in URLs.')
        except (ValidationError, TypeError, AttributeError) as exc:
            raise ValueError(f'{title}: provide a verified HTTP(S) delivery URL.') from exc
        kind = entry.get('module_type', Module.MODULE_TYPE_SPLICE_SMART_CONTENT)
        if kind not in {Module.MODULE_TYPE_IMPORTED, Module.MODULE_TYPE_SPLICE_SMART_CONTENT, Module.MODULE_TYPE_EXTERNAL_LINK}:
            raise ValueError(f'{title}: this importer accepts URL activities only.')
        protocols = entry.get('supported_protocols', [])
        if not isinstance(protocols, list) or not protocols or any(p not in ['splice', 'html', 'pitt', 'lti'] for p in protocols):
            raise ValueError(f'{title}: valid supported_protocols are required.')
        provider = entry.get('provider_id')
        if not isinstance(provider, str) or not provider.strip() or len(provider) > 255:
            raise ValueError(f'{title}: provider_id is required.')
        content_data = entry.get('content_data', {})
        recommendation_only = entry.get('is_recommendation_only', False)
        if not isinstance(recommendation_only, bool):
            raise ValueError(f'{title}: is_recommendation_only must be boolean.')
        if not isinstance(content_data, dict):
            raise ValueError(f'{title}: content_data must be an object.')
        for field in ('description', 'platform_name', 'author', 'keywords'):
            value = entry.get(field, '')
            if not isinstance(value, str) or (field != 'description' and len(value) > (500 if field == 'keywords' else 255)):
                raise ValueError(f'{title}: invalid {field}.')
        result.append({
            'title': title.strip(), 'content_url': url, 'provider_id': provider,
            'module_type': kind, 'supported_protocols': protocols, 'content_data': content_data,
            'order': index * 10, 'is_visible': True, 'is_locked': False,
            'is_recommendation_only': recommendation_only,
            **{field: entry.get(field, '') for field in ('description', 'platform_name', 'author', 'keywords')},
        })
    description = unit.get('description', '')
    if not isinstance(description, str):
        raise ValueError('Unit description must be text.')
    return unit['title'].strip(), description, result


@transaction.atomic
def import_unit_package(course_id, raw, *, apply=False, expected_sha256=None):
    title, description, modules = validate_unit_package(raw)
    digest = hashlib.sha256(raw).hexdigest()
    course = Course.objects.select_for_update().get(pk=course_id)
    if course.is_locked_for_research:
        raise ValueError('Research-locked courses cannot be changed.')
    existing = list(Unit.objects.filter(course=course, title__iexact=title))
    if existing:
        unit = existing[0]
        current = list(unit.modules.order_by('order', 'id'))
        if len(existing) != 1 or unit.title != title or unit.description != description or len(current) != len(modules) or any(
                any(getattr(item, key) != value for key, value in wanted.items()) for item, wanted in zip(current, modules)):
            raise ValueError('A different unit with this title already exists. No existing content was changed.')
        return {'course_id': course.pk, 'unit': title, 'modules': len(modules), 'sha256': digest, 'action': 'already_present'}
    report = {'course_id': course.pk, 'unit': title, 'modules': len(modules), 'sha256': digest, 'action': 'append_unit'}
    if not apply:
        return report
    if expected_sha256 != digest:
        raise ValueError('Review the dry-run and supply its SHA256 using --expect-sha256.')
    order = (Unit.objects.filter(course=course).aggregate(value=Max('order'))['value'] or 0) + 10
    unit = Unit.objects.create(course=course, title=title, description=description, order=order)
    for values in modules:
        Module.objects.create(unit=unit, **values)
    return {**report, 'applied': True, 'unit_id': unit.pk}
