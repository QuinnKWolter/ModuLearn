"""Validated public metadata for current ACOS catalog exercises."""
import json
import re
from django.core.cache import cache
from .slc_catalog import _fetch


def catalog_goals(params):
    def first(key):
        value = params.get(key, '')
        return value[0] if isinstance(value, list) and value else value
    example = str(first('example-id') or first('example_id') or '')
    match = re.search(r'__([a-fA-F0-9]{24})$', example)
    if not match:
        return None
    key = 'acos-catalog-goals:v1:' + match[1]
    goals = cache.get(key)
    if goals is None:
        try:
            payload = json.loads(_fetch(f'https://acos.cs.vt.edu/static/acos-pcex-examples/data/{match[1]}.json'))
            if isinstance(payload, list) and len(payload) == 1:
                payload = payload[0]
            goals = payload.get('activityGoals') if isinstance(payload, dict) else None
            if not isinstance(goals, list) or not all(isinstance(g, dict) for g in goals):
                return None
            cache.set(key, goals, 3600)
        except (ValueError, OSError):
            return None
    index = first('index')
    if index != '':
        try:
            index = int(index)
            return [goals[index]] if 0 <= index < len(goals) else None
        except (ValueError, TypeError):
            return None
    return goals
