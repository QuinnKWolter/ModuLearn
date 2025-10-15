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
def mockup_student_dashboard(request):
    """
    Displays the mockup student dashboard with learning analytics.
    """
    return render(request, 'dashboard/mockup_student_dashboard.html', {
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
        
        # Make request to external API
        api_url = 'http://adapt2.sis.pitt.edu/aggregate2/GetContentLevels'
        
        print(f"Making request to: {api_url}")
        print(f"Parameters: {params}")
        
        try:
            # Add network diagnostics
            import socket
            print(f"DNS Resolution test:")
            try:
                ip = socket.gethostbyname('adapt2.sis.pitt.edu')
                print(f"  adapt2.sis.pitt.edu resolves to: {ip}")
            except socket.gaierror as dns_error:
                print(f"  DNS resolution failed: {dns_error}")
                return JsonResponse({
                    'error': f'DNS resolution failed: {str(dns_error)}'
                }, status=500)
            
            # Test basic connectivity
            print(f"Testing basic connectivity to {ip}:80...")
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10)
                result = sock.connect_ex((ip, 80))
                sock.close()
                if result == 0:
                    print(f"  Basic connectivity test: SUCCESS")
                else:
                    print(f"  Basic connectivity test: FAILED (error code: {result})")
                    return JsonResponse({
                        'error': f'Cannot connect to {ip}:80 (error code: {result})'
                    }, status=500)
            except Exception as conn_error:
                print(f"  Basic connectivity test failed: {conn_error}")
                return JsonResponse({
                    'error': f'Connectivity test failed: {str(conn_error)}'
                }, status=500)
            
            # Try with different request configurations
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            print(f"Attempting request with headers: {headers}")
            response = requests.get(api_url, params=params, headers=headers, timeout=30)
            print(f"Request successful! Status: {response.status_code}")
            
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            print(f"Request details - URL: {api_url}")
            print(f"Request details - Params: {params}")
            
            # Try alternative approach with session
            try:
                print("Trying with requests.Session()...")
                session = requests.Session()
                session.headers.update(headers)
                response = session.get(api_url, params=params, timeout=30)
                print(f"Session request successful! Status: {response.status_code}")
            except requests.exceptions.RequestException as e2:
                print(f"Session request also failed: {e2}")
                return JsonResponse({
                    'error': f'Failed to connect to external API: {str(e)}. Session fallback also failed: {str(e2)}'
                }, status=500)
        
        if response.status_code != 200:
            return JsonResponse({
                'error': f'API request failed with status {response.status_code}',
                'details': response.text
            }, status=response.status_code)
        
        # Get the response text
        response_text = response.text.strip()
        print(f"Raw response: {response_text[:200]}...")  # Log first 200 chars
        print(f"Response size: {len(response_text)} characters")
        
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
                    
                    print(f"Node.js return code: {result.returncode}")
                    print(f"Node.js stdout: {result.stdout[:200]}...")
                    print(f"Node.js stderr: {result.stderr}")
                    
                    if result.returncode == 0:
                        # Parse the JSON output from Node.js
                        data = json.loads(result.stdout)
                        print("Successfully parsed using Node.js")
                    else:
                        raise Exception(f"Node.js failed with return code {result.returncode}: {result.stderr}")
                        
                except subprocess.TimeoutExpired:
                    print("Node.js execution timed out")
                    raise Exception("Node.js execution timed out after 30 seconds")
                except FileNotFoundError:
                    print("Node.js not found in PATH")
                    raise Exception("Node.js is not installed or not in PATH")
                finally:
                    # Clean up the temporary file
                    import os
                    try:
                        os.unlink(temp_file_path)
                    except:
                        pass  # Ignore cleanup errors
                
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
        import traceback
        print(f"Unexpected error: {e}")
        print(f"Full traceback: {traceback.format_exc()}")
        return JsonResponse({
            'error': f'An unexpected error occurred: {str(e)}',
            'traceback': traceback.format_exc()
        }, status=500)