"""Deterministic coverage planning for the public SLC integration test course."""
from collections import defaultdict

SUPPORTED_DELIVERIES = {'SPLICE', 'HTML', 'PITT', 'LTI', 'LTI 1.1'}


def coverage_groups(records):
    groups = defaultdict(list)
    for record in records:
        provider = (record.get('attribution') or {}).get('provider') or 'Unspecified'
        kind = (record.get('identity') or {}).get('type') or 'Unspecified'
        for protocol in {str(d.get('protocol') or 'UNKNOWN').upper() for d in record.get('delivery', [])} or {'UNKNOWN'}:
            groups[(provider, kind, protocol)].append(record)
    return dict(sorted(groups.items()))


def candidate_order(record):
    identity = record.get('identity') or {}
    title = identity.get('title', '')
    language = str((record.get('languages') or {}).get('content_language') or '').lower()
    simple = ('hello', 'adding two', 'addition', 'using int', 'select-from', 'selecting one', 'variables', 'odd or even')
    return (str(record.get('status', '')).startswith('broken'), language not in {'en', 'english'},
            not any(word in title.lower() for word in simple), -len(record.get('delivery', [])), len(title), title, record['id'])


def coverage_key(provider, kind, protocol):
    return '|'.join((provider, kind, protocol))
