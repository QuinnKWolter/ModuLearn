"""Deterministic source/message inventory; no database or network access.

Coverage is catalog coverage, not proof that every runtime sentence is translated.
New unmarked template text is reported for review alongside explicit message keys.
"""
import ast
import html
import json
import re
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

from .i18n import catalog


SKIP_DIRS = {'staticfiles', 'node_modules', 'media', 'fixtures', 'migrations',
             'locales', 'tests', '__pycache__', 'management'}
LITERAL = r'''(["'])(.*?)(?<!\\)\1'''
MARKER = re.compile(r'''(?:\{%\s*(?:ui|trans)\s+|\b(?:t|ui|translate|gettext|gettext_lazy)\(\s*)''' + LITERAL)
TEMPLATE_TAG = re.compile(r'\{%.*?%\}|\{\{.*?\}\}', re.S)


def normalize(value):
    return html.unescape(re.sub(r'\s+', ' ', value)).strip()


def decode_literal(value):
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return value[1:-1]


class VisibleText(HTMLParser):
    """Find unmarked interface fragments, excluding authored/protected content."""
    def __init__(self):
        super().__init__()
        self.stack = []
        self.items = set()

    def add(self, value):
        for fragment in TEMPLATE_TAG.split(value):
            fragment = normalize(fragment)
            if re.search('[a-zA-Z]', fragment) and not re.search(r'[{}=<>]|https?://', fragment):
                self.items.add(fragment)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        protected = tag in ('script', 'style', 'code', 'pre', 'textarea') or 'data-no-ui-translate' in attrs or attrs.get('translate') == 'no'
        hidden = protected or any(skip for _, skip in self.stack)
        if not hidden:
            for name in ('title', 'aria-label', 'alt', 'placeholder'):
                if attrs.get(name): self.add(attrs[name])
        if tag not in ('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'):
            self.stack.append((tag, hidden))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if not any(skip for _, skip in self.stack): self.add(data)


def build_inventory(root, languages):
    source_catalog = catalog('en')
    references = defaultdict(set)
    explicit = set()
    candidates = defaultdict(set)
    for path in sorted(Path(root).rglob('*')):
        relative = path.relative_to(root)
        if path.suffix not in ('.html', '.js', '.py') or any(part in SKIP_DIRS for part in relative.parts): continue
        if path.name.startswith('test') or path.name in ('translation_audit.py', 'i18n.py', 'ui_i18n.py'): continue
        text = path.read_text(encoding='utf-8')
        source = relative.as_posix()
        for match in MARKER.finditer(text):
            key = decode_literal(match[1] + match[2] + match[1])
            if key == '{count} ': continue  # Implemented by ui_count below.
            explicit.add(key)
            references[key].add(source)
        # Conditional messages must catalogue both branches, not only t('literal').
        for match in re.finditer(r'''\bt\([^,;()]*\?\s*(["'])(.*?)\1\s*:\s*(["'])(.*?)\3''', text):
            for quote, value in ((match[1], match[2]), (match[3], match[4])):
                key = decode_literal(quote + value + quote)
                explicit.add(key)
                references[key].add(source)
        for match in re.finditer(r'''\{%\s*ui_count\s+["']([^"']+)["']\s+["']([^"']+)["']''', text):
            for noun in match.groups():
                key = '{count} ' + noun
                explicit.add(key)
                references[key].add(source)
        normalized = normalize(text)
        # Include legacy exact-match DOM strings and server-returned UI labels.
        for key in source_catalog:
            if key in normalized: references[key].add(source)
        if path.suffix == '.html':
            cleaned = re.sub(r'\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}', '', text, flags=re.S)
            cleaned = re.sub(r'\{%\s*block\s+(?:body_class|page_class)\s*%\}.*?\{%\s*endblock\s*%\}', '', cleaned, flags=re.S)
            parser = VisibleText()
            parser.feed(cleaned)
            for key in parser.items - source_catalog.keys(): candidates[key].add(source)
    problems = []
    summaries = {}
    tokens = lambda value: set(re.findall(r'\{\w+\}', value))
    for language in languages:
        messages = catalog(language)
        missing = sorted(set(source_catalog) - messages.keys())
        extra = sorted(set(messages) - source_catalog.keys())
        invalid = sorted(key for key, value in messages.items() if not isinstance(value, str) or not value.strip() or tokens(key) != tokens(value))
        if missing or extra or invalid: problems.append({'language': language, 'missing': missing, 'extra': extra, 'invalid': invalid})
        summaries[language] = {'messages': len(messages), 'missing': len(missing), 'invalid': len(invalid)}
    missing_keys = sorted(explicit - source_catalog.keys())
    if missing_keys: problems.append({'uncatalogued_messages': missing_keys})
    # Invert references so a maintainer can see every catalogued item per page.
    pages = defaultdict(list)
    for key, paths in sorted(references.items()):
        for path in sorted(paths): pages[path].append(key)
    return {
        'scope': 'Shared ModuLearn UI. Authored course/research content and external provider frames retain their original language.',
        'coverage_note': 'Catalog parity and source references are automated. Runtime dialogs and new unmarked text still require browser review.',
        'languages': summaries,
        'errors': problems,
        'unmarked_template_text_for_review': {key: sorted(paths) for key, paths in sorted(candidates.items())},
        'pages': dict(sorted(pages.items())),
    }


def serialize_inventory(report):
    return json.dumps(report, ensure_ascii=False, indent=2) + '\n'
