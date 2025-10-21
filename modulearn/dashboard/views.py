from django.shortcuts import render, redirect
from courses.models import Enrollment, Course, CourseInstance
from django.contrib.auth.decorators import login_required
import requests
from django.http import JsonResponse
from courses.utils import get_course_auth_token
import json
from urllib.parse import urlparse
from py_mini_racer import MiniRacer

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
    try:
        token = get_course_auth_token(request.user)
        return JsonResponse({"token": token})
    except ValueError as e:
        print(f"Error: {e}")
        return JsonResponse({"error": str(e)}, status=401)
    except requests.exceptions.RequestException as e:
        return JsonResponse({"error": f"Request error: {e}"}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"An unexpected error occurred during token request: {e}"}, status=500)

@login_required
def mockup_dashboard(request):
    """
    Displays the mockup dashboard with learning analytics.
    """
    return render(request, 'dashboard/mockup_dashboard.html', {
        'user': request.user
    })

@login_required
def fetch_analytics_data(request):
    """
    Proxy endpoint to fetch analytics data from external ADAPT2 API.
    Handles network restrictions by using host.docker.internal on production.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    api_url = "" # Initialize to avoid potential unbound variable
    try:
        # Get parameters from request
        params = {
            'usr': request.GET.get('usr', 'jab464'),
            'grp': request.GET.get('grp', 'CMPINF0401Fall20242'),
            'sid': request.GET.get('sid', '5A195'),
            'cid': request.GET.get('cid', '417'),
            'mod': request.GET.get('mod', 'all'),
            'models': request.GET.get('models', '-1'),
            'avgtop': request.GET.get('avgtop', '-1'),
            'removeZeroProgressUsers': request.GET.get('removeZeroProgressUsers', 'true')
        }
        
        # Use different URLs based on DEBUG setting
        from django.conf import settings
        if settings.DEBUG:
            # In local development, hit the remote server directly
            api_url = 'http://adapt2.sis.pitt.edu/aggregate2/GetContentLevels'
        else:
            # In production (on pawscomp2), hit the server itself
            api_url = 'http://host.docker.internal/aggregate2/GetContentLevels'
        
        print(f"Making request to: {api_url}")
        
        # --- This is the simplification ---
        # No more complex fallback logic. Just make the one, correct request.
        response = requests.get(api_url, params=params, timeout=30)
        
        # This is a cleaner way to check for non-200 status codes
        response.raise_for_status() 
        
        response_text = response.text.strip()
        print(f"Raw response: {response_text[:200]}...")

        # --- Parse the response - it's a full JS object with functions ---
        try:
            # 1. Create a sandboxed JS runtime
            ctx = MiniRacer()

            # 2. Evaluate the response text and stringify it to proper JSON
            # We wrap the response in parentheses to evaluate it as an expression
            json_string = ctx.eval(f"JSON.stringify(({response_text}))")

            # 3. Now parse the clean, valid JSON string
            data = json.loads(json_string)

        except Exception as e:
            # This will catch any JS evaluation errors
            print(f"Failed to parse response with MiniRacer: {e}")
            print(f"Response length: {len(response_text)} characters")
            print(f"First 500 chars: {response_text[:500]}")
            return JsonResponse({
                'error': 'Failed to parse JavaScript response from upstream API',
                'details': str(e),
            }, status=502) # 502 Bad Gateway

        print(f"Successfully parsed data with keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
        return JsonResponse(data)

    # --- Simplified Error Handling ---
    except requests.exceptions.HTTPError as e:
        # Catches non-200 status codes from raise_for_status()
        print(f"API request failed with status {e.response.status_code}: {e}")
        return JsonResponse({
            'error': f'Upstream API returned status {e.response.status_code}',
            'details': e.response.text
        }, status=502) # 502 Bad Gateway

    except requests.exceptions.RequestException as e:
        # Catches network errors (timeout, connection refused, DNS failure)
        hostname = urlparse(api_url).hostname if api_url else "unknown"
        print(f"Request to {hostname} failed: {e}")
        return JsonResponse({
            'error': f'Failed to connect to upstream service at {hostname}.',
            'details': str(e)
        }, status=503) # 503 Service Unavailable

    except Exception as e:
        # Catch any other unexpected errors
        print(f"Unexpected error: {e}")
        return JsonResponse({
            'error': f'An unexpected error occurred: {str(e)}'
        }, status=500)