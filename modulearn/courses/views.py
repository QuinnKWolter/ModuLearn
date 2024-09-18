from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Course, Module, Enrollment, ModuleProgress
from django.contrib.auth import get_user_model

User = get_user_model()

def course_list(request):
    """
    Displays a list of all available courses.
    """
    courses = Course.objects.all()
    return render(request, 'courses/course_list.html', {'courses': courses})

@login_required
def course_detail(request, course_id):
    """
    Displays details of a specific course and handles enrollment.
    """
    course = get_object_or_404(Course, id=course_id)
    enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()

    if request.method == 'POST' and not enrolled and request.user.is_student:
        Enrollment.objects.create(student=request.user, course=course)
        messages.success(request, f'You have enrolled in {course.title}.')
        return redirect('courses:course_detail', course_id=course_id)

    return render(request, 'courses/course_detail.html', {'course': course, 'enrolled': enrolled})

@login_required
def module_detail(request, course_id, module_id):
    """
    Displays details of a specific module within a course.
    """
    course = get_object_or_404(Course, id=course_id)
    module = get_object_or_404(Module, id=module_id, course=course)
    enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()

    if not enrolled:
        messages.error(request, 'You must be enrolled in the course to access modules.')
        return redirect('courses:course_detail', course_id=course_id)

    # Retrieve or create module progress
    enrollment = Enrollment.objects.get(student=request.user, course=course)
    module_progress, created = ModuleProgress.objects.get_or_create(
        enrollment=enrollment, module=module
    )

    return render(request, 'courses/module_detail.html', {'module': module})
