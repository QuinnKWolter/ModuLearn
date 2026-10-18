"""Resolve provider callbacks to one enrolled session, without guessing."""
import logging
from courses.models import CourseInstance
from django.db.models import Q

logger = logging.getLogger(__name__)


def enrolled_tracking_session(course, user, params):
    def value(key):
        item = params.get(key, '')
        return item[0] if isinstance(item, list) and item else item

    sessions = CourseInstance.objects.filter(course=course, active=True).filter(
        Q(enrollments__student=user, enrollments__active=True, enrollments__is_instructor_preview=False)
        | Q(instructors=user)).distinct()
    instance_id = value('course_instance_id')
    if instance_id:
        if not str(instance_id).isdecimal():
            return None
        # Session IDs survive renaming, unlike the provider's display group.
        return sessions.filter(pk=instance_id).first()
    if value('grp'):
        sessions = sessions.filter(group_name=value('grp'))
    matches = list(sessions.distinct()[:2])
    if len(matches) != 1:
        logger.warning('Provider progress has no unique enrolled session; include course_instance_id (course=%s)', course.pk)
        return None
    return matches[0]
