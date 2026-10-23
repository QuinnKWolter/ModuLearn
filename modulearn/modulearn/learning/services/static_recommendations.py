"""Import wide recommendation CSVs and resolve them against a course's modules."""
import csv
import hashlib
import io
import math
import re
from collections import defaultdict

from django.urls import reverse

from courses.models import Module, ModuleProgress
from .access_rules import evaluate_module_access, evaluate_unit_access
from .course_plugins import is_course_plugin_enabled


def normalized(value):
    return ' '.join(str(value or '').casefold().split())


def provider(value):
    value = normalized(value)
    return {'jsvee': 'animatedexamples', 'jsvee-java': 'animatedexamples', 'pcex_challenge': 'pcex_ch'}.get(value, value)


def parse_uploads(files):
    if not 1 <= len(files) <= 3:
        raise ValueError('Upload one recommendations CSV and, optionally, its assignments and medoids CSVs (one course/run at a time).')
    tables, provenance, families = {}, [], set()
    for upload in files:
        raw = upload.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError('Each CSV must be smaller than 10 MiB.')
        try:
            reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
            fields = reader.fieldnames or []
            if len(fields) != len(set(fields)):
                raise ValueError('Duplicate CSV column names.')
            rows = []
            for row in reader:
                if len(rows) >= 50000 or None in row or any(value is None for value in row.values()):
                    raise ValueError('Invalid or oversized CSV rows.')
                rows.append(row)
        except (UnicodeDecodeError, csv.Error) as exc:
            raise ValueError('CSV files must contain valid UTF-8 text and CSV quoting.') from exc
        columns = set(fields)
        if {'query_item', 'query_provider', 'query_topic'}.issubset(columns):
            kind = 'recommendations'
        elif {'SubjectID', 'item_name', 'provider_id', 'topic_name', 'kc_cluster'}.issubset(columns):
            kind = 'assignments'
        elif {'kc_cluster', 'raw_pattern', 'normalized_pattern', 'subtree_code'}.issubset(columns):
            kind = 'medoids'
        else:
            raise ValueError(f'{upload.name}: unrecognized CSV format.')
        if kind in tables or not rows:
            raise ValueError('Use exactly one nonempty CSV of each kind; do not mix email1 and email2 versions.')
        tables[kind] = rows
        family = re.match(r'(CS0*7|CMPINF0*401)[_\-]', upload.name, re.I)
        if family:
            families.add(re.sub(r'0+(?=\d)', '', family[1].upper()))
        provenance.append({'name': upload.name, 'kind': kind, 'rows': len(rows), 'sha256': hashlib.sha256(raw).hexdigest()})
    if 'recommendations' not in tables or len(families) > 1:
        raise ValueError('Include the recommendations CSV and only companion files from the same course.')
    assignments = tables.get('assignments', [])
    medoids = {r['kc_cluster']: r for r in tables.get('medoids', [])}
    if len(medoids) != len(tables.get('medoids', [])):
        raise ValueError('Duplicate medoid clusters. Use files from a single run.')
    if medoids and assignments and {r['kc_cluster'] for r in assignments} != set(medoids):
        raise ValueError('Assignment clusters do not match these medoids. Use files from the same run.')
    activity_rows = defaultdict(list)
    for row in assignments:
        activity_rows[(provider(row['provider_id']), normalized(row['item_name']))].append(row)
    # A provider/title pair can identify several genuinely different exercises.
    # Preserve each supplied code variant instead of overwriting its source code.
    target_variants = defaultdict(set)
    for row in tables['recommendations']:
        for column, name in row.items():
            match = re.fullmatch(r'(.+)_rank_(\d+)_item', column)
            if match and name.strip():
                snippet = row.get(column[:-5] + '_code', '').replace('\r\n', '\n').strip()
                target_variants[(provider(match[1]), normalized(name))].add(snippet)
    nodes, code, edges = {}, {}, []
    def node(name, source, topic='', snippet='', *, is_target=False):
        name = name.strip()
        if not name:
            raise ValueError('An activity name is missing.')
        source = provider(source)
        if not source:
            raise ValueError('An activity provider is missing.')
        rows = activity_rows[(source, normalized(name))]
        if assignments and not rows:
            raise ValueError(f'{name}: activity missing from the assignments file. Use companion files from the same course/run.')
        topics = {r['topic_name'] for r in rows}
        if not topic and len(topics) == 1:
            topic = next(iter(topics))
        identity = '\x1f'.join((source, normalized(name), normalized(topic)))
        variant = ''
        if is_target and len(target_variants.get((source, normalized(name)), ())) > 1:
            variant = hashlib.sha256(snippet.replace('\r\n', '\n').strip().encode()).hexdigest()[:12]
            identity += '\x1f' + variant
        key = hashlib.sha256(identity.encode()).hexdigest()[:24]
        nodes[key] = {'title': name, 'provider': source, 'topic': topic,
                      'clusters': sorted({r['kc_cluster'] for r in rows if not topic or normalized(r['topic_name']) == normalized(topic)})}
        if variant:
            nodes[key]['code_variant'] = variant
        if snippet:
            code[key] = snippet
        return key
    queries = set()
    for number, row in enumerate(tables['recommendations'], 2):
        src = node(row['query_item'], row['query_provider'], row['query_topic'], row.get('query_code', ''))
        if src in queries:
            raise ValueError(f'Row {number}: duplicate query activity.')
        queries.add(src)
        columns = [key for key in row if re.fullmatch(r'.+_rank_\d+_item', key)]
        if not columns:
            raise ValueError('Expected provider_rank_N_item/code/similarity columns.')
        for column in columns:
            if not row[column].strip():
                continue
            match = re.fullmatch(r'(.+)_rank_(\d+)_item', column)
            if int(match[2]) < 1:
                raise ValueError('Recommendation ranks must start at 1.')
            prefix = column[:-5]
            try:
                similarity = float(row[prefix + '_similarity'])
                if not math.isfinite(similarity) or not -1 <= similarity <= 1:
                    raise ValueError
            except (KeyError, ValueError):
                raise ValueError(f'Row {number}: {prefix} needs a cosine similarity between -1 and 1.') from None
            target = node(row[column], match[1], snippet=row.get(prefix + '_code', ''), is_target=True)
            edges.append({'source': src, 'target': target, 'rank': int(match[2]), 'similarity': similarity, 'provider': provider(match[1])})
    if not edges:
        raise ValueError('No recommendation links were found.')
    return {'nodes': nodes, 'edges': edges, 'analysis': {'code': code, 'assignments': assignments,
            'medoids': medoids, 'recommendations': tables['recommendations']}, 'provenance': provenance}


def resolve_nodes(dataset, course):
    modules = list(Module.objects.filter(unit__course=course).select_related('unit'))
    by_id = {m.pk: m for m in modules}
    resolved, issues = {}, []
    for key, node in dataset.nodes.items():
        if key in dataset.bindings:
            module = by_id.get(dataset.bindings[key])
            candidates = [module] if module else []
        else:
            titled = [m for m in modules if normalized(m.title) == normalized(node['title'])]
            candidates = [m for m in titled
                          if provider(m.provider_id or m.platform_name) == node['provider']]
            if node['topic']:
                in_topic = [m for m in candidates if normalized(m.unit.title) == normalized(node['topic'])]
                if in_topic:
                    candidates = in_topic
            # Keep specific matches authoritative. Only relax provider metadata
            # when it found nothing; never select an arbitrary duplicate.
            if not candidates:
                candidates = titled
                if node['topic']:
                    in_topic = [m for m in titled if normalized(m.unit.title) == normalized(node['topic'])]
                    if in_topic:
                        candidates = in_topic
        needs_variant_match = bool(node.get('code_variant') and key not in dataset.bindings)
        if len(candidates) == 1 and not needs_variant_match:
            resolved[key] = candidates[0]
        else:
            issues.append({'key': key, **node, 'reason': 'Code variant requires explicit match' if candidates and needs_variant_match else 'Ambiguous match' if candidates else 'No matching activity',
                           'candidates': [m.pk for m in candidates]})
    return resolved, issues, modules


def source_keys_by_module(dataset, resolved, modules):
    """URL imports can bind a problem to several placements; attempts stay separate."""
    ordinary_ids = {m.pk for m in modules if not m.is_recommendation_only}
    result = defaultdict(set)
    for key, module in resolved.items():
        result[module.pk].add(key)
        for module_id in dataset.nodes[key].get('source_module_ids', []):
            if module_id in ordinary_ids:
                result[module_id].add(key)
    return result


def recommendations_for(enrollment):
    from .recommendation_tracking import practice_items
    return practice_items(enrollment)
