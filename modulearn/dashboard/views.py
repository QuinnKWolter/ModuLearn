from django.shortcuts import render, redirect
from courses.models import Enrollment, Course, CourseInstance
from django.contrib.auth.decorators import login_required
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import uuid
from accounts.models import User
from courses.utils import get_course_auth_token
import json
import re

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
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
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
        
        # Make request to external API via internal proxy to handle network restrictions
        # Use different URLs based on DEBUG setting
        from django.conf import settings
        if settings.DEBUG:
            # In development, use the remote server
            api_url = 'http://adapt2.sis.pitt.edu/aggregate2/GetContentLevels'
        else:
            # In production, use localhost
            api_url = 'http://localhost/aggregate2/GetContentLevels'
        
        print(f"Making request to: {api_url}")
        print(f"Parameters: {params}")
        
        # Try direct request first, fallback to proxy if it fails
        from urllib.parse import urlencode
        
        try:
            # Try direct request first (works locally)
            print(f"Attempting direct request to: {api_url}")
            response = requests.get(api_url, params=params, timeout=30)
            response_text = response.text
            print(f"Direct request successful with status: {response.status_code}")
            
            if response.status_code != 200:
                raise requests.RequestException(f"API returned status {response.status_code}")
                
        except requests.RequestException as e:
            print(f"Direct request failed: {e}")
            
            # For localhost requests, don't try proxy - just return the error
            from urllib.parse import urlparse
            parsed_url = urlparse(api_url)
            
            if parsed_url.hostname in ['localhost', '127.0.0.1']:
                print(f"Localhost request failed - service may not be running on {parsed_url.hostname}")
                return JsonResponse({
                    'error': f'Localhost service not available. Please ensure the ADAPT2 service is running on {parsed_url.hostname}. Error: {str(e)}'
                }, status=503)
            
            # For other hosts, try proxy as fallback
            if parsed_url.hostname in getattr(settings, 'PROXY_ALLOWED_HOSTS', set()):
                print("Falling back to internal proxy...")
                
                # Fallback to internal proxy
                try:
                    # Build the full URL with parameters for proxy
                    full_api_url = f"{api_url}?{urlencode(params)}"
                    print(f"Proxy URL: {full_api_url}")
                    
                    # Make internal request to our own proxy endpoint
                    base_url = request.build_absolute_uri('/').rstrip('/')
                    proxy_url = f"{base_url}/proxy/"
                    
                    print(f"Making internal proxy request to: {proxy_url}")
                    proxy_response = requests.get(proxy_url, params={'url': full_api_url}, timeout=30)
                    
                    if proxy_response.status_code != 200:
                        error_content = proxy_response.text
                        print(f"Proxy request failed with status {proxy_response.status_code}: {error_content}")
                        return JsonResponse({
                            'error': f'Both direct and proxy requests failed. Proxy status: {proxy_response.status_code}',
                            'details': error_content
                        }, status=503)
                    
                    response_text = proxy_response.text
                    print(f"Proxy request successful")
                    
                except Exception as proxy_error:
                    print(f"Proxy request also failed: {proxy_error}")
                    return JsonResponse({
                        'error': f'Both direct request and proxy failed. Direct: {str(e)}, Proxy: {str(proxy_error)}'
                    }, status=503)
            else:
                print(f"Host {parsed_url.hostname} not in allowed hosts, cannot use proxy")
                return JsonResponse({
                    'error': f'Direct request failed and host {parsed_url.hostname} not allowed for proxy. Error: {str(e)}'
                }, status=503)
        
        print(f"Response size: {len(response_text)} characters")
        
        # Clean up the response text
        response_text = response_text.strip()
        print(f"Raw response: {response_text[:200]}...")  # Log first 200 chars
        
        # Debug: Check for specific problematic patterns
        print(f"Contains 'function': {'function' in response_text}")
        print(f"Contains 'Math.': {'Math.' in response_text}")
        print(f"Contains 'var ': {'var ' in response_text}")
        
        # Count lines with unquoted property names
        unquoted_lines = [line for line in response_text.split('\n') if re.search(r'^\s*\w+:', line)]
        print(f"Contains unquoted property names: {len(unquoted_lines)} lines")
        
        # Check if response is too large (safety check)
        if len(response_text) > 1000000:  # 1MB limit
            print("Warning: Response is very large, may cause memory issues")
        
        # Parse the response - it's a JavaScript object literal, not JSON
        try:
            # First try standard JSON parsing
            data = response.json()
        except json.JSONDecodeError:
            try:
                # If JSON parsing fails, try to evaluate as JavaScript object literal
                # Use subprocess to call Node.js to parse the JavaScript object literal
                print("Standard JSON parsing failed, trying to evaluate as JS object literal using Node.js...")
                
                import subprocess
                import tempfile
                
                # Create a temporary file with the JavaScript code
                with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as temp_file:
                    # Write a Node.js script that parses the object and outputs JSON
                    temp_file.write(f"""
const data = {response_text};
console.log(JSON.stringify(data, null, 2));
""")
                    temp_file_path = temp_file.name
                
                try:
                    # Run the Node.js script
                    result = subprocess.run(['node', temp_file_path], 
                                          capture_output=True, text=True, timeout=30)
                    
                    if result.returncode == 0:
                        # Parse the JSON output from Node.js
                        data = json.loads(result.stdout)
                        print("Successfully parsed using Node.js")
                    else:
                        raise Exception(f"Node.js failed: {result.stderr}")
                        
                finally:
                    # Clean up the temporary file
                    import os
                    os.unlink(temp_file_path)
                
            except Exception as eval_error:
                import traceback
                print(f"Failed to parse response as JS object literal: {eval_error}")
                print(f"Response length: {len(response_text)} characters")
                print(f"First 500 chars: {response_text[:500]}")
                print(f"Last 500 chars: {response_text[-500:]}")
                
                # Print full stack trace
                print("Full stack trace:")
                traceback.print_exc()
                
                # Try to find the exact line where it fails
                if hasattr(eval_error, 'lineno'):
                    print(f"Error at line {eval_error.lineno}")
                    # Show the problematic line
                    lines = response_text.split('\n')
                    if eval_error.lineno <= len(lines):
                        print(f"Problematic line {eval_error.lineno}: {lines[eval_error.lineno-1]}")
                        # Show context around the error
                        start = max(0, eval_error.lineno - 3)
                        end = min(len(lines), eval_error.lineno + 2)
                        print("Context around error:")
                        for i in range(start, end):
                            marker = ">>> " if i == eval_error.lineno - 1 else "    "
                            print(f"{marker}{i+1:4d}: {lines[i]}")
                
                return JsonResponse({
                    'error': 'Unable to parse response data',
                    'details': str(eval_error),
                    'stack_trace': traceback.format_exc()
                }, status=500)
        
        print(f"Successfully parsed data with keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
        
        return JsonResponse(data)
        
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return JsonResponse({
            'error': f'Request error: {str(e)}'
        }, status=500)
    except Exception as e:
        print(f"Unexpected error: {e}")
        return JsonResponse({
            'error': f'An unexpected error occurred: {str(e)}'
        }, status=500)