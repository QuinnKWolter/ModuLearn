"""Pedagogical grouping, independent of legacy recommendation provider labels.

Catalog types take precedence over editable display labels and provider aliases.
Unknown types stay in Similar Activities; no title-based content guessing.
"""
import re
from urllib.parse import urlsplit


def _key(value):
    return re.sub(r'[^a-z0-9]', '', str(value or '').lower())


TYPES = {
    'freecodingproblems': 'coding', 'freecoding': 'coding',
    'codingproblems': 'coding', 'independentdevelopment': 'coding',
    'codecompletionproblem': 'completion', 'codecompletion': 'completion',
    'completionproblems': 'completion', 'programmingchallenges': 'completion',
    'predictingfinalresult': 'tracing', 'parameterizedcodetracing': 'tracing',
    'codetracing': 'tracing', 'tracingproblems': 'tracing',
    'workedexample': 'worked_example', 'workedexamples': 'worked_example',
    'programmingexamples': 'worked_example', 'behaviorexample': 'worked_example',
    'codevisualization': 'animation', 'animations': 'animation',
}
PROVIDERS = {
    'pcrs': 'coding', 'sqlknot': 'coding', 'codeworkout': 'coding',
    'pcexch': 'completion', 'pcex': 'worked_example',
    'quizjet': 'tracing', 'quizpet': 'tracing',
    'animatedexamples': 'animation', 'jsvee': 'animation',
}
PREFERRED = {
    'coding': {'completion', 'worked_example'},
    'completion': {'worked_example'},
    'tracing': {'animation'},
}


def activity_kind(module, fallback_provider=''):
    data = module.content_data if isinstance(module.content_data, dict) else {}
    catalog = data.get('catalog') or {}
    metadata = catalog.get('metadata') or {} if isinstance(catalog, dict) else {}
    identity = metadata.get('identity') or {} if isinstance(metadata, dict) else {}
    declared = identity.get('type') if isinstance(identity, dict) else None
    provider = _key(module.provider_id or fallback_provider)
    if _key(declared) in TYPES:
        return TYPES[_key(declared)]
    # Cupcake's CodeConstruction records are explanation-based worked examples.
    if _key(declared) == 'codeconstruction' and provider == 'cupcake':
        return 'worked_example'
    if _key(declared) == 'codeconstruction' and provider in {'pcex', 'pcexch'}:
        return 'completion'
    for field in ('activityType', 'activity_type'):
        if _key(data.get(field)) in TYPES:
            return TYPES[_key(data[field])]
    url = urlsplit(module.content_url or '')
    if '/cupcake/' in url.path:
        # Published Cupcake engine filenames survive imports without catalog metadata.
        path = (url.path + '/' + url.fragment.split('?')[0]).lower()
        for token, kind in [('code-completion', 'completion'), ('worked-example', 'worked_example'),
                            ('code-tracing', 'tracing'), ('free-coding', 'coding')]:
            if token in path:
                return kind
    label = _key(module.platform_name)
    return TYPES.get(label) or PROVIDERS.get(provider) or PROVIDERS.get(_key(fallback_provider)) or 'other'


def recommendation_tier(source, target, provider=''):
    return ('recommended' if activity_kind(target, provider) in PREFERRED.get(activity_kind(source), set())
            else 'similar')
