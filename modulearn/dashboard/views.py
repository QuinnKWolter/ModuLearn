from django.shortcuts import render, redirect
from courses.models import Enrollment, Course, CourseInstance
from django.contrib.auth.decorators import login_required
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import uuid
from accounts.models import User

@login_required
def student_dashboard(request):
    """
    Displays the student's dashboard with enrolled courses.
    """
    enrollments = Enrollment.objects.filter(
        student=request.user
    ).select_related(
        'course_instance',
        'course_instance__course',
        'course_progress'
    ).order_by('-course_instance__created_at')
    
    return render(request, 'dashboard/student_dashboard.html', {
        'enrollments': enrollments
    })

@login_required
def instructor_dashboard(request):
    """
    Displays the instructor's dashboard with their courses and course instances.
    """
    if not request.user.is_instructor:
        return redirect('dashboard:student_dashboard')
        
    courses = Course.objects.filter(instructors=request.user)
    course_instances = CourseInstance.objects.filter(
        instructors=request.user
    ).select_related('course').prefetch_related(
        'enrollments',
        'enrollments__course_progress',
        'enrollments__student'
    )
    
    return render(request, 'dashboard/instructor_dashboard.html', {
        'courses': courses,
        'course_instances': course_instances
    })

@login_required
def generate_course_auth_url(request):
    """
    Generates an encrypted token for course authoring login.
    """
    if not request.user.is_authenticated:
        print("Error: User not authenticated")
        return JsonResponse({"error": "User not authenticated"}, status=401)

    # Fetch user details
    user_email = request.user.email
    user_fullname = f"{request.user.first_name} {request.user.last_name}"

    # Generate or retrieve stored password
    user = request.user
    if not user.course_authoring_password:
        user.course_authoring_password = str(uuid.uuid4())  # Generate a UUID password
        user.save()

    # Create payload
    payload = {
        "fullname": user_fullname,
        "email": user_email,
        "password": user.course_authoring_password,
    }

    print(f"Payload for token request: {payload}")

    # Make POST request to obtain the encrypted token
    try:
        response = requests.post(
            "http://adapt2.sis.pitt.edu/next.course-authoring/api/auth/x-login-token",
            json=payload
        )
        response.raise_for_status()
        print(f"Raw response content: {response.content}")

        # Extract token
        token = response.text.strip()
        print(f"Token received: {token}")
    except requests.exceptions.RequestException as e:
        print(f"Request exception occurred: {e}")
        return JsonResponse({"error": f"Request error: {e}"}, status=500)

    return JsonResponse({"token": token})
