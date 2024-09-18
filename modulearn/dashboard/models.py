from django.shortcuts import render
from courses.models import Enrollment, Course

def student_dashboard(request):
    enrollments = Enrollment.objects.filter(student=request.user)
    return render(request, 'dashboard/student_dashboard.html', {'enrollments': enrollments})

def instructor_dashboard(request):
    courses = Course.objects.filter(instructors=request.user)
    return render(request, 'dashboard/instructor_dashboard.html', {'courses': courses})
