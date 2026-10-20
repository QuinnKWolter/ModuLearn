"""Persistent instructor activity testing, excluded from student enrollment lists."""
from courses.models import Enrollment


def testing_enrollment(user, instance):
    if not instance.instructors.filter(pk=user.pk).exists():
        return None
    enrollment, _ = Enrollment.all_objects.get_or_create(student=user, course_instance=instance,
        defaults={'is_instructor_preview': True})
    if not enrollment.is_instructor_preview:
        enrollment.is_instructor_preview = True
        enrollment.save(update_fields=['is_instructor_preview'])
    return enrollment
