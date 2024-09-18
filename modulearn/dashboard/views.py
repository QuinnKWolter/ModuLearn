from django.shortcuts import render
from courses.models import Enrollment, Course
from django.contrib.auth.decorators import login_required

@login_required
def student_dashboard(request):
    """
    Displays the student's dashboard with enrolled courses.
    """
    enrollments = Enrollment.objects.filter(student=request.user)
    return render(request, 'dashboard/student_dashboard.html', {'enrollments': enrollments})

@login_required
def instructor_dashboard(request):
    """
    Displays the instructor's dashboard with their courses.
    """
    courses = Course.objects.filter(instructors=request.user)
    return render(request, 'dashboard/instructor_dashboard.html', {'courses': courses})
