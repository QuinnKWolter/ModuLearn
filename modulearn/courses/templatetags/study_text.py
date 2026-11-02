"""Small, deliberately HTML-free Markdown subset for authored study text."""
import re
from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


def inline(text):
    # Escape before adding a fixed set of tags. No raw HTML, images or URL schemes.
    pieces = re.split(r'(`[^`\n]+`)', str(text))
    result = []
    for piece in pieces:
        if piece.startswith('`') and piece.endswith('`'):
            result.append('<code>' + str(escape(piece[1:-1])) + '</code>')
        else:
            value = str(escape(piece))
            value = re.sub(r'\*\*([^*\n]+)\*\*', r'<strong>\1</strong>', value)
            value = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<em>\1</em>', value)
            result.append(value)
    return ''.join(result)


@register.filter
def study_markdown(value):
    result, code, in_code, in_list = [], [], False, False
    for line in str(value or '').splitlines():
        if line.startswith('```'):
            if in_list:
                result.append('</ul>'); in_list = False
            if in_code:
                result.append('<pre><code>' + str(escape('\n'.join(code))) + '</code></pre>'); code = []
            in_code = not in_code
            continue
        if in_code:
            code.append(line)
            continue
        if line.startswith(('- ', '* ')):
            if not in_list:
                result.append('<ul>'); in_list = True
            result.append('<li>' + inline(line[2:]) + '</li>')
            continue
        if in_list:
            result.append('</ul>'); in_list = False
        heading = re.match(r'^(#{1,3})\s+(.+)$', line)
        if heading:
            level = len(heading[1]) + 1
            result.append(f'<h{level}>' + inline(heading[2]) + f'</h{level}>')
        elif line:
            result.append('<div>' + inline(line) + '</div>')
        else:
            result.append('<br>')
    if in_code:
        result.append('<pre><code>' + str(escape('\n'.join(code))) + '</code></pre>')
    if in_list:
        result.append('</ul>')
    return mark_safe(''.join(result))
