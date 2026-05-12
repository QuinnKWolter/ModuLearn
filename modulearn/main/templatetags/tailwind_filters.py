"""
Template filters for adding Tailwind CSS classes to Django form widgets.
Replaces django-crispy-forms functionality.

Usage:
  {% load tailwind_filters %}
  {{ form.field|add_class:"form-control" }}
"""
from django import template

register = template.Library()


@register.filter(name='add_class')
def add_class(field, css_class):
    """Add a CSS class to a form field widget."""
    if hasattr(field, 'as_widget'):
        existing = field.field.widget.attrs.get('class', '')
        classes = f'{existing} {css_class}'.strip()
        return field.as_widget(attrs={'class': classes})
    return field


@register.filter(name='tw_input')
def tw_input(field):
    """Apply standard Tailwind form-control classes to a field."""
    widget_type = field.field.widget.__class__.__name__
    if widget_type in ('CheckboxInput',):
        css = 'w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-700'
    elif widget_type in ('Select', 'SelectMultiple'):
        css = 'form-select'
    elif widget_type in ('Textarea',):
        css = 'form-control min-h-[100px]'
    else:
        css = 'form-control'
    existing = field.field.widget.attrs.get('class', '')
    classes = f'{existing} {css}'.strip()
    return field.as_widget(attrs={'class': classes})
