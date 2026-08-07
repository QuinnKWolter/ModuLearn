from django.conf import settings


DEFAULT_MAX_STUDENTS_PER_SESSION = 500
DEFAULT_MAX_SESSIONS_PER_COURSE = 100
DEFAULT_MAX_ACTIVE_SESSIONS_PER_INSTRUCTOR = 250


class CapacityLimitError(ValueError):
    """Raised when a course/session capacity limit would be exceeded."""


def max_students_per_session():
    return int(getattr(settings, "MAX_STUDENTS_PER_SESSION", DEFAULT_MAX_STUDENTS_PER_SESSION))


def max_sessions_per_course():
    return int(getattr(settings, "MAX_SESSIONS_PER_COURSE", DEFAULT_MAX_SESSIONS_PER_COURSE))


def max_active_sessions_per_instructor():
    return int(
        getattr(
            settings,
            "MAX_ACTIVE_SESSIONS_PER_INSTRUCTOR",
            DEFAULT_MAX_ACTIVE_SESSIONS_PER_INSTRUCTOR,
        )
    )


def active_session_enrollment_count(course_instance):
    return course_instance.enrollments.filter(active=True).count()


def remaining_session_student_slots(course_instance):
    return max(0, max_students_per_session() - active_session_enrollment_count(course_instance))


def ensure_session_student_capacity(course_instance, additional=1):
    additional = max(0, int(additional or 0))
    remaining = remaining_session_student_slots(course_instance)
    if additional > remaining:
        limit = max_students_per_session()
        raise CapacityLimitError(
            f"This session can have at most {limit} active students. "
            f"{remaining} slot{'s' if remaining != 1 else ''} remain."
        )


def active_course_session_count(course):
    if course is None:
        return 0
    return course.instances.filter(active=True).count()


def remaining_course_session_slots(course):
    return max(0, max_sessions_per_course() - active_course_session_count(course))


def ensure_course_session_capacity(course, additional=1):
    if course is None:
        return
    additional = max(0, int(additional or 0))
    remaining = remaining_course_session_slots(course)
    if additional > remaining:
        limit = max_sessions_per_course()
        raise CapacityLimitError(
            f"This course can have at most {limit} active sessions. "
            f"{remaining} slot{'s' if remaining != 1 else ''} remain."
        )


def active_instructor_session_count(instructor):
    from courses.models import CourseInstance

    return CourseInstance.objects.filter(
        instructors=instructor,
        active=True,
    ).distinct().count()


def remaining_instructor_session_slots(instructor):
    return max(0, max_active_sessions_per_instructor() - active_instructor_session_count(instructor))


def ensure_instructor_session_capacity(instructor, additional=1):
    additional = max(0, int(additional or 0))
    remaining = remaining_instructor_session_slots(instructor)
    if additional > remaining:
        limit = max_active_sessions_per_instructor()
        raise CapacityLimitError(
            f"An instructor can manage at most {limit} active sessions. "
            f"{remaining} slot{'s' if remaining != 1 else ''} remain."
        )
