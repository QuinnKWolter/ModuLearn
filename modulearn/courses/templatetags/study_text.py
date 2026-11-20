"""Shared, HTML-free CommonMark + GFM renderer for authored learning content."""
from django import template
from django.utils.safestring import mark_safe
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

register = template.Library()

# No raw HTML or executable URLs. Task boxes are display-only: survey responses
# must use actual form questions so their answers are saved and exported.
# Keep authored single newlines visible, as the previous renderer did.
_markdown = MarkdownIt("gfm-like", {"html": False, "breaks": True, "xhtmlOut": False}).use(tasklists_plugin, label=True)
_validate_link = _markdown.validateLink
_markdown.validateLink = lambda url: _validate_link(url) and not url.strip().lower().startswith("data:")


@register.filter
def study_markdown(value):
    return mark_safe(_markdown.render(str(value or "")))
