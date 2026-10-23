"""Completion for AnnEx: opening every annotated line, not merely launching."""
import hashlib
import json
import logging
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit, unquote
from django.core.cache import cache
from .slc_catalog import _fetch

logger = logging.getLogger(__name__)


class AnnotationLines(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lines = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'annotated-comment' in attrs.get('class', '').split() and attrs.get('data-line', '').isdecimal():
            self.lines.add(attrs['data-line'])


def annotation_metadata(module):
    parsed = urlsplit(module.content_url)
    if parsed.hostname != 'acos.cs.vt.edu' or not parsed.path.startswith('/html/annotated/'):
        return None
    url = urlunsplit(('https', parsed.hostname, parsed.path, '', ''))
    key = 'annotated-lines:v2:' + hashlib.sha256(url.encode()).hexdigest()
    metadata = cache.get(key)
    if metadata is None:
        try:
            parser = AnnotationLines()
            html = _fetch(url)
            parser.feed(html)
            # AnnEx creates its comment elements in the browser from this
            # JSON object; server-rendered variants expose them directly.
            match = re.search(r"window\.annotated\s*=\s*\{\s*['\"][^'\"]+['\"]\s*:\s*", html)
            if match:
                example, _ = json.JSONDecoder().raw_decode(html[match.end():])
                parser.lines.update(str(i) for i, line in enumerate(example.get('lines', []), 1) if line.get('comment'))
            metadata = {'example': unquote(parsed.path.rstrip('/').split('/')[-1]), 'lines': sorted(parser.lines)}
            cache.set(key, metadata, 86400)
        except Exception:
            logger.warning('Unable to retrieve AnnEx annotation metadata for activity %s', module.pk, exc_info=True)
            return None
    return metadata


def apply_annotation_event(progress, message, metadata):
    data = message.get('data', {})
    if not metadata or not isinstance(data, dict) or data.get('exampleId') != metadata['example'] or data.get('type') != 'open':
        return
    expected = set(metadata['lines'])
    line = str(data.get('line', ''))
    if not expected or line not in expected:
        return
    state = progress.state_data if isinstance(progress.state_data, dict) else {}
    viewed = set(state.get('annotated_viewed_lines', [])) & expected
    # A transient metadata outage must not discard previously saved opens.
    # Reconcile from the durable interaction log once metadata is available.
    logged_lines = progress.events.filter(
        source='splice', event_type='provider_event',
        payload__splice__data__exampleId=metadata['example'],
        payload__splice__data__type='open',
    ).values_list('payload__splice__data__line', flat=True).distinct()
    viewed.update(str(value) for value in logged_lines if str(value) in expected)
    viewed.add(line)
    fraction = len(viewed) / len(expected)
    from .progress import apply_progress_snapshot
    apply_progress_snapshot(progress, source='annotated', progress=max(progress.progress or 0, fraction),
        score=max(progress.score or 0, fraction * 100), success=progress.success or fraction == 1,
        is_complete=progress.is_complete or fraction == 1,
        payload={'annotated_viewed_lines': sorted(viewed), 'annotated_total_lines': len(expected)},
        event_type='progress')
