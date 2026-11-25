"""Select guides from the rendered interface; this never grants access."""
from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def page_guide(context):
    request = context.get('request')
    if not request or context.get('study_shell') or context.get('participant_session'):
        return None
    user = getattr(request, 'user', None)
    if getattr(user, 'is_anonymous_participant', False):
        return None
    match = getattr(request, 'resolver_match', None)
    view = match.view_name if match else ''
    guide = None
    if view in {'main:home', 'main:home_overview', 'main:home_students', 'main:home_teachers', 'main:home_researchers'}:
        guide = 'home'
    elif view in {'main:info', 'main:about', 'main:contact'}:
        guide = 'overview'
    elif view == 'dashboard:instructor_dashboard' and context.get('effective_is_instructor'):
        guide = 'instructor'
    elif view == 'dashboard:student_dashboard' and getattr(user, 'is_authenticated', False):
        guide = 'student'
    elif view == 'courses:course_configuration':
        guide = 'configuration'
    elif view == 'courses:course_detail' and (context.get('is_enrolled') or context.get('is_instructor')):
        guide = 'course'
    elif view == 'recruitment:studio':
        guide = 'study'
    if not guide:
        return None
    return {'id': guide, 'identity': str(user.pk) if getattr(user, 'is_authenticated', False) else 'visitor'}
