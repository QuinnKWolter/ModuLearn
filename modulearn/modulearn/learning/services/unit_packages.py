"""Portable, append-only unit packages. Never import learner data or database IDs."""
from copy import deepcopy
import base64
from datetime import datetime
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from courses.models import Module, Unit, ModuleBranchRule
from courses.utils import export_course_to_json, _restore_content_file, ensure_module_form
from .access_rules import next_order_for_unit, sync_module_progress_for_course

SCHEMA = 'modulearn.unit.v2'


def parse_schedule(opens, closes, zone=None):
    def parse(value):
        if not value:
            return None
        result = value if isinstance(value, datetime) else parse_datetime(str(value))
        if result is None:
            raise ValueError('Enter a valid date and time.')
        if timezone.is_naive(result):
            from zoneinfo import ZoneInfo
            from datetime import timezone as dt_timezone
            tz = ZoneInfo(zone) if zone else timezone.get_current_timezone()
            aware = timezone.make_aware(result, tz)
            if aware.astimezone(dt_timezone.utc).astimezone(tz).replace(tzinfo=None) != result:
                raise ValueError('This local time does not exist because of a daylight-saving change. Choose another time.')
            if aware.utcoffset() != aware.replace(fold=1).utcoffset():
                raise ValueError('This local time occurs twice because of a daylight-saving change. Choose an unambiguous time.')
            return aware
        return result
    opens, closes = parse(opens), parse(closes)
    if opens and closes and closes <= opens:
        raise ValueError('The closing date must be after the opening date.')
    return opens, closes


def export_unit(unit):
    payload = export_course_to_json(unit.course, unit_ids=[unit.id])
    data = payload['units'][0]
    # Use package-local IDs, including when two modules share a title.
    ids = {str(m['id']): f'm{index}' for index, m in enumerate(data['modules'])}
    warnings = []
    for item in [data, *data['modules']]:
        rule = deepcopy(item.get('unlock_rule') or {})
        for condition in rule.get('conditions', []):
            if condition.get('type') in {'module_completed', 'module_accessed'}:
                target = ids.get(str(condition.pop('target_id', '')))
                condition['target_ref'] = target
                if not target:
                    warnings.append('An unlock condition refers outside this unit. Resolve it after import.')
            elif 'target_id' in condition and condition['type'] != 'condition_equals':
                condition.pop('target_id')
                condition['target_ref'] = None
                warnings.append('An external unlock condition requires review after import.')
        item['unlock_rule'] = rule
        item.pop('unlock_rule_portable', None)
    for item in data['modules']:
        item['ref'] = ids[str(item.pop('id'))]
    data.pop('id', None)
    data.pop('activities', None)
    branches = []
    for rule in unit.course.branch_rules.filter(Q(source_module__unit=unit) | Q(target_module__unit=unit)):
        source, target = ids.get(str(rule.source_module_id)), ids.get(str(rule.target_module_id))
        if source and target:
            branches.append(dict(source_ref=source, target_ref=target, condition_type=rule.condition_type,
                threshold=rule.threshold, required_study_condition=rule.required_study_condition,
                priority=rule.priority, active=rule.active))
        else:
            warnings.append('A cross-unit adaptive branch must be recreated after import.')
            if target:
                item = next(item for item in data['modules'] if item['ref'] == target)
                item['is_locked'] = True
                item['unlock_rule'] = {'conditions': [{'type': 'unresolved_import'}]}
    return {'schema': SCHEMA, 'unit': data, 'branch_rules': branches, 'warnings': sorted(set(warnings))}


def import_unit(course, payload):
    files = []
    try:
        with transaction.atomic():
            return _import_unit(course, payload, files)
    except Exception:
        for name in files:
            default_storage.delete(name)
        raise


def _import_unit(course, payload, files):
    if isinstance(payload, dict) and payload.get('format') == 'modulearn.unit.v1':
        import json
        from .unit_import import validate_unit_package
        title, description, modules = validate_unit_package(json.dumps(payload).encode())
        payload = {'schema': SCHEMA, 'unit': {'title': title, 'description': description,
                   'modules': [dict(module, ref=f'm{index}') for index, module in enumerate(modules)]}}
    if not isinstance(payload, dict) or payload.get('schema') != SCHEMA:
        raise ValueError('Upload a ModuLearn unit export (modulearn.unit.v2).')
    data = payload.get('unit')
    if not isinstance(data, dict) or not isinstance(data.get('modules'), list):
        raise ValueError('The unit must contain a list of activities.')
    if len(data['modules']) > 1000:
        raise ValueError('A unit package may contain at most 1,000 activities.')
    title = str(data.get('title') or data.get('name') or '').strip()
    if not title or len(title) > 255:
        raise ValueError('A unit title of 1–255 characters is required.')
    opens, closes = parse_schedule(data.get('opens_at'), data.get('closes_at'))
    unit = Unit.objects.create(course=course, title=title, description=data.get('description') or '',
        order=next_order_for_unit(course), is_visible=data.get('is_visible', True) is True,
        is_locked=data.get('is_locked', False) is True, opens_at=opens, closes_at=closes)
    lookup, pending = {}, [(unit, data.get('unlock_rule'))]
    warnings = [str(warning) for warning in payload.get('warnings', []) if isinstance(warning, str)]
    for index, activity in enumerate(data['modules']):
        if not isinstance(activity, dict) or not isinstance(activity.get('ref'), str) or not activity['ref'] or activity['ref'] in lookup:
            raise ValueError('Every activity needs a unique package reference.')
        module_title = str(activity.get('title') or activity.get('name') or '').strip()
        module_type = activity.get('module_type', Module.MODULE_TYPE_IMPORTED)
        if not module_title or len(module_title) > 255 or module_type not in dict(Module.MODULE_TYPE_CHOICES):
            raise ValueError('A activity has an invalid title or type.')
        values = {key: deepcopy(activity[key]) for key in (
            'description', 'content_url', 'provider_id', 'platform_name', 'author',
            'supported_protocols', 'content_data', 'keywords', 'resource_link_id'
        ) if key in activity}
        if values.get('content_url'):
            try:
                URLValidator(schemes=['http', 'https'])(values['content_url'])
            except ValidationError:
                raise ValueError('Activity URLs must use HTTP or HTTPS.') from None
        for key, default in [('is_visible', True), ('is_locked', False), ('allow_resubmission', True),
                             ('is_graded', True), ('is_recommendation_only', False)]:
            values[key] = activity.get(key, default) is True
        if values['is_recommendation_only']:
            values['is_graded'] = False
        module = Module.objects.create(unit=unit, title=module_title, module_type=module_type,
                                       order=(index + 1) * 10, **values)
        file_data = activity.get('content_file')
        if file_data and (not isinstance(file_data, dict) or not file_data.get('data_base64')):
            raise ValueError('A file activity is missing its embedded file. Export it again from the source.')
        if file_data:
            try:
                base64.b64decode(file_data['data_base64'], validate=True)
            except (ValueError, TypeError):
                raise ValueError('Invalid embedded file data.') from None
        if _restore_content_file(module, activity):
            files.append(module.content_file.name)
            module.save(update_fields=['content_file'])
        if module_type in Module.FORM_LIKE_TYPES:
            ensure_module_form(module, activity.get('form'))
        lookup[activity['ref']] = module
        pending.append((module, activity.get('unlock_rule')))
    for obj, raw_rule in pending:
        rule = deepcopy(raw_rule or {})
        if not isinstance(rule, dict) or not isinstance(rule.get('conditions', []), list):
            raise ValueError('Invalid unlock conditions.')
        for condition in rule.get('conditions', []):
            if not isinstance(condition, dict):
                raise ValueError('Invalid unlock condition.')
            if 'target_ref' in condition:
                target = lookup.get(condition.pop('target_ref'))
                if target:
                    condition['target_id'] = target.id
                else:
                    # Fail closed. Never accidentally unlock a unit with missing prerequisites.
                    condition.clear()
                    condition['type'] = 'unresolved_import'
                    obj.is_locked = True
                    warnings.append('An external prerequisite could not be imported; its item remains locked until configured.')
            elif condition.get('type') != 'condition_equals':
                condition.pop('target_id', None)
        obj.unlock_rule = rule
        obj.save(update_fields=['unlock_rule', 'is_locked'])
    for rule in payload.get('branch_rules', []):
        if not isinstance(rule, dict) or rule.get('source_ref') not in lookup or rule.get('target_ref') not in lookup:
            raise ValueError('An adaptive branch has an invalid activity reference.')
        if rule.get('condition_type') not in dict(ModuleBranchRule.CONDITION_CHOICES):
            raise ValueError('Invalid adaptive branch condition.')
        ModuleBranchRule.objects.create(course=course, source_module=lookup[rule['source_ref']],
            target_module=lookup[rule['target_ref']], **{key:rule[key] for key in
            ('condition_type', 'threshold', 'required_study_condition', 'priority', 'active') if key in rule})
    for module in lookup.values():
        if not module.is_recommendation_only:
            sync_module_progress_for_course(module)
    from .grading import refresh_course_grades
    refresh_course_grades(course)
    return unit, sorted(set(warnings))
