from __future__ import annotations

from courses.models import Course, CourseInstance, Enrollment
from modulearn.integrations.config import get_course_authoring_base_url
from modulearn.integrations.course_authoring import (
    build_course_authoring_app_url,
    build_x_login_url,
)
from modulearn.core.roles import get_user_role_snapshot

from .timelines import get_course_instance_recent_activity, get_course_timeline_for_student, get_student_timeline


def build_student_dashboard_context(user):
    enrollments = Enrollment.objects.filter(student=user).select_related(
        "course_instance",
        "course_instance__course",
        "course_progress",
    ).order_by("-course_instance__created_at")

    course_instances = []
    for index, enrollment in enumerate(enrollments):
        course_instance = enrollment.course_instance
        course_instance.user_enrollment = enrollment
        course_instance.timeline = get_course_timeline_for_student(course_instance, user, limit=4)
        course_instance.is_expanded = index == 0
        course_instances.append(course_instance)

    return {
        "enrollments": enrollments,
        "course_instances": course_instances,
        "lti_data": getattr(user, "lti_data", {}) or {},
        "timeline": get_student_timeline(user, limit=12),
    }


def build_instructor_dashboard_context(user):
    courses = Course.objects.filter(instructors=user)
    course_instances = CourseInstance.objects.filter(instructors=user).select_related("course").prefetch_related(
        "enrollments",
        "enrollments__course_progress",
        "enrollments__student",
    )

    for instance in course_instances:
        enrollments = list(instance.enrollments.all())
        if enrollments:
            total_progress = sum(enrollment.course_progress.overall_progress for enrollment in enrollments)
            total_score = sum(enrollment.course_progress.overall_score for enrollment in enrollments)
            instance.avg_progress = total_progress / len(enrollments)
            instance.avg_score = total_score / len(enrollments)
        else:
            instance.avg_progress = 0
            instance.avg_score = 0
        instance.recent_activity = get_course_instance_recent_activity(instance, limit=5)

    student_enrollments = Enrollment.objects.filter(student=user).select_related(
        "course_instance",
        "course_instance__course",
        "course_progress",
    )
    enrolled_instances = []
    for enrollment in student_enrollments:
        instance = enrollment.course_instance
        instance.user_enrollment = enrollment
        if instance not in course_instances:
            enrolled_instances.append(instance)

    for instance in enrolled_instances:
        enrollments = list(instance.enrollments.all())
        if enrollments:
            total_progress = sum(enrollment.course_progress.overall_progress for enrollment in enrollments)
            total_score = sum(enrollment.course_progress.overall_score for enrollment in enrollments)
            instance.avg_progress = total_progress / len(enrollments)
            instance.avg_score = total_score / len(enrollments)
        else:
            instance.avg_progress = 0
            instance.avg_score = 0
        instance.recent_activity = get_course_instance_recent_activity(instance, limit=3)

    role_snapshot = get_user_role_snapshot(user)
    show_legacy_groups_section = bool(user.kt_login or user.kt_user_id or getattr(user, "kt_groups", None))

    return {
        "courses": courses,
        "course_instances": course_instances,
        "enrolled_instances": enrolled_instances,
        "legacy_groups": [],
        "legacy_group_count": None,
        "show_legacy_groups_section": show_legacy_groups_section or role_snapshot["effective_is_instructor"],
        "recent_timeline": get_student_timeline(user, limit=8, event_types=("completion", "outcome")),
        "course_authoring_base_url": get_course_authoring_base_url(),
        "course_authoring_x_login_url": build_x_login_url(),
        "course_authoring_app_url": build_course_authoring_app_url(),
    }
