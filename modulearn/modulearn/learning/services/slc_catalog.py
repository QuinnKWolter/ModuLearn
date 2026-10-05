"""Read-only adapters for the public Pitt and SPLICE catalogs.

Only fixed upstream hosts are fetched. Imported items retain the full upstream
record; listing responses intentionally carry just searchable summary metadata.
"""
import json
import logging
import re
import ssl
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.core.cache import cache
from django.utils.html import strip_tags

PITT_API = 'https://adapt2.sis.pitt.edu/next.course-authoring/api/catalog-v2'
SPLICE_CATALOG = 'https://splice.cs.vt.edu/catalog/'
SOURCES = {'pitt': 'Pitt SLC', 'splice': 'SPLICE'}
FRESH_SECONDS = 3600
STALE_SECONDS = 86400
MAX_BYTES = 20 * 1024 * 1024
logger = logging.getLogger(__name__)


class CatalogUnavailable(ValueError):
    pass


def _tls_context(url):
    context = ssl.create_default_context()
    if urlsplit(url).hostname == urlsplit(PITT_API).hostname:
        # Pitt currently serves only its leaf certificate. Supply the missing
        # public intermediates, but still require a system-trusted root.
        context.load_verify_locations(cafile=str(Path(__file__).with_name('certificates') / 'pitt-intermediates.pem'))
        context.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN
    return context


def _fetch(url):
    request = Request(url, headers={'User-Agent': 'ModuLearn Catalog/1.0', 'Accept': 'application/json,text/html'})
    with urlopen(request, timeout=15, context=_tls_context(url)) as response:
        if urlsplit(response.url).hostname != urlsplit(url).hostname:
            raise ValueError('Unexpected catalog redirect')
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('Catalog response is too large')
    return data.decode('utf-8')


def _cached(key, loader):
    key = 'slc-catalog:v1:' + key
    try:
        previous = cache.get(key)
    except Exception:
        logger.warning('Catalog cache read failed for %s', key, exc_info=True)
        previous = None
    if previous and time.time() - previous['at'] < FRESH_SECONDS:
        return previous['data'], False
    try:
        data = loader()
    except Exception:
        logger.warning('Catalog fetch failed for %s', key, exc_info=True)
        if previous:
            return previous['data'], True
        raise CatalogUnavailable('The catalog is temporarily unavailable. Please try again shortly.') from None
    try:
        cache.set(key, {'data': data, 'at': time.time()}, STALE_SECONDS)
    except Exception:
        # A database/cache write error must not discard a successful fetch.
        logger.warning('Catalog cache write failed for %s', key, exc_info=True)
    return data, False


def _load_list(source):
    text = _fetch(PITT_API if source == 'pitt' else SPLICE_CATALOG)
    if source == 'pitt':
        data = json.loads(text)
    else:
        # SPLICE publishes its complete search dataset in this JSON assignment.
        match = re.search(r'window\.allItems\s*=\s*', text)
        if not match:
            raise ValueError('SPLICE search data not found')
        data, _ = json.JSONDecoder().raw_decode(text[match.end():])
    if not isinstance(data, list) or not data or not all(isinstance(item, dict) and item.get('id') for item in data):
        raise ValueError('Invalid catalog dataset')
    return data


def safe_url(value):
    if not isinstance(value, str):
        return ''
    try:
        parts = urlsplit(value.strip())
        if parts.scheme in {'http', 'https'} and parts.hostname and not parts.username and not parts.password:
            return value.strip()
    except ValueError:
        pass
    return ''


def _strings(value):
    return [str(item).strip() for item in (value if isinstance(value, list) else [value]) if item]


def _plain(value):
    return strip_tags(str(value or '')).strip()


def normalize_item(source, raw, *, detail=False):
    if source == 'pitt':
        identity = raw.get('identity') or {}
        attribution = raw.get('attribution') or {}
        languages = raw.get('languages') or {}
        classification = raw.get('classification') or {}
        endpoints = [{'protocol': str(e.get('protocol') or '').upper(), 'url': safe_url(e.get('url'))}
                     for e in raw.get('delivery', []) if isinstance(e, dict)]
        tags = [tag.split(';color=')[0] for tag in _strings(raw.get('tags'))]
        concepts = []
        for category in (classification.get('knowledge_components') or {}).values():
            if isinstance(category, dict):
                concepts.extend(_strings(category.get('concepts')))
        item = {
            'title': _plain(identity.get('title')) or 'Untitled content',
            'description': _plain((raw.get('content') or {}).get('prompt')),
            'type': identity.get('type') or 'Learning activity',
            'provider': attribution.get('provider') or 'Unspecified',
            'authors': [a.get('name', '') for a in attribution.get('authors', []) if isinstance(a, dict)],
            'languages': _strings(languages.get('programming_languages')),
            'content_languages': _strings(languages.get('content_language')),
            'tags': tags, 'concepts': sorted(set(concepts)),
            'license': (raw.get('rights') or {}).get('license') or 'Unspecified',
            'status': raw.get('status') or 'public', 'updated': raw.get('listed_at') or '',
            'demo_url': safe_url((raw.get('links') or {}).get('demo_url')),
            'catalog_url': 'https://adapt2.sis.pitt.edu/next.course-authoring/#/catalog-v2/' + str(raw['id']),
        }
    else:
        endpoints = [{'protocol': str(protocol).upper(), 'url': safe_url(url)}
                     for protocol, url in zip(raw.get('protocol') or [], raw.get('protocol_url') or [])]
        item = {
            'title': _plain(raw.get('title')) or 'Untitled content',
            'description': _plain(raw.get('description')),
            'type': ', '.join(_strings(raw.get('features'))) or 'Learning activity',
            'provider': raw.get('platform_name') or 'Unspecified',
            'authors': _strings(raw.get('author')),
            'languages': _strings(raw.get('programming_language')),
            'content_languages': _strings(raw.get('natural_language')),
            'tags': _strings(raw.get('keywords')), 'concepts': [],
            'license': raw.get('license') or 'Unspecified', 'status': 'public', 'updated': '',
            'demo_url': safe_url(raw.get('iframe_url')) or safe_url(raw.get('persistentID')),
            'catalog_url': SPLICE_CATALOG,
        }
    item.update(id=str(raw['id']), source=source, source_label=SOURCES[source],
                protocols=sorted({e['protocol'] for e in endpoints if e['protocol']}))
    if detail:
        usable = [e for e in endpoints if e['url']]
        rank = {'SPLICE': 0, 'HTML': 1, 'PITT': 2, 'LTI 1.1': 3, 'LTI': 3}
        usable.sort(key=lambda e: rank.get(e['protocol'], 4))
        # Never invent a delivery URL from a protocol name or a demo URL.
        selected = usable[0] if usable else None
        item.update(delivery=endpoints, selected_delivery=selected, metadata=raw)
    return item


def catalog_items(source=''):
    if source and source not in SOURCES:
        raise ValueError('Choose a valid catalog.')
    items, warnings = [], []
    for key in ([source] if source else SOURCES):
        try:
            records, stale = _cached(key + ':list', lambda: _load_list(key))
            items.extend(normalize_item(key, raw) for raw in records)
            if stale:
                warnings.append(f'{SOURCES[key]} is unavailable; showing its last cached results.')
        except CatalogUnavailable:
            warnings.append(f'{SOURCES[key]} is temporarily unavailable. Retry shortly or use the other catalog.')
    if not items:
        raise CatalogUnavailable(' '.join(warnings))
    return items, warnings


def catalog_item(source, item_id):
    item_id = str(item_id)
    if source not in SOURCES or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', item_id):
        raise ValueError('Choose a valid catalog item.')
    if source == 'pitt':
        def loader():
            raw = json.loads(_fetch(PITT_API + '/' + item_id))
            if not isinstance(raw, dict) or str(raw.get('id')) != item_id or not raw.get('identity'):
                raise ValueError('Catalog item not found')
            return raw
        raw, stale = _cached('pitt:item:' + item_id, loader)
    else:
        records, stale = _cached('splice:list', lambda: _load_list('splice'))
        raw = next((r for r in records if str(r['id']) == item_id), None)
        if raw is None:
            raise ValueError('This item is no longer in the catalog. Refresh the catalog and try again.')
    item = normalize_item(source, raw, detail=True)
    item['stale'] = stale
    return item


def module_catalog_fields(item):
    endpoint = item['selected_delivery']
    if not endpoint:
        raise ValueError('This item does not publish a usable delivery URL. You can still explore its demo.')
    if item['status'].startswith('broken'):
        raise ValueError('This item is marked broken by its catalog. Choose another activity.')
    protocol = endpoint['protocol'].lower()
    protocol = 'lti' if protocol.startswith('lti') else protocol
    provider = item['provider'].lower()
    if provider == 'pcex' and item['type'] in {'CodeCompletionProblem', 'CodeConstruction'}:
        provider = 'pcex_ch'
    return {
        'content_url': endpoint['url'], 'supported_protocols': [protocol],
        'platform_name': item['provider'][:255], 'provider_id': provider[:255],
        'author': ', '.join(item['authors'])[:255],
        'keywords': ', '.join(item['tags'] + item['concepts'])[:500],
        'content_data': {'catalog': {'source': item['source'], 'id': item['id'],
                                   'selected_delivery': endpoint, 'metadata': item['metadata']}},
    }
