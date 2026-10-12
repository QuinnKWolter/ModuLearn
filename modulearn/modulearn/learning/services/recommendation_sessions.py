"""Recommendation configuration belongs to a teaching session, not a course."""
from courses.models import CourseInstance, StaticRecommendationSet


def recommendations_enabled(instance):
    return StaticRecommendationSet.objects.filter(course_instance=instance, enabled=True).exists()


def resolve_session(course_id, instance_id=None):
    if instance_id is not None:
        return CourseInstance.objects.get(pk=instance_id, course_id=course_id)
    instances = list(CourseInstance.objects.filter(course_id=course_id)[:2])
    if len(instances) != 1:
        raise ValueError('Specify the course session; recommendation changes cannot apply to multiple sessions implicitly.')
    return instances[0]
