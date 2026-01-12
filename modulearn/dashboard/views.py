from django.shortcuts import render, redirect
from courses.models import Enrollment, Course, CourseInstance
from django.contrib.auth.decorators import login_required
import requests
from django.http import JsonResponse
from courses.utils import get_course_auth_token, reset_course_authoring_password
import json
from urllib.parse import urlparse
from .kt_utils import get_user_groups_with_course_ids, get_course_resources, has_kt_session, get_kt_login_url, has_kt_session, get_kt_login_url
import logging

logger = logging.getLogger(__name__)

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
    
    # Calculate stats for each course instance
    for instance in course_instances:
        enrollments = instance.enrollments.all()
        if enrollments:
            total_progress = sum(e.course_progress.overall_progress for e in enrollments)
            total_score = sum(e.course_progress.overall_score for e in enrollments)
            instance.avg_progress = total_progress / len(enrollments)
            instance.avg_score = total_score / len(enrollments)
        else:
            instance.avg_progress = 0
            instance.avg_score = 0
    
    # Get enrollments where instructor is enrolled as student
    student_enrollments = Enrollment.objects.filter(
        student=request.user
    ).select_related('course_instance', 'course_instance__course', 'course_progress')
    
    # Add enrolled course instances to the list
    enrolled_instances = []
    for enrollment in student_enrollments:
        instance = enrollment.course_instance
        instance.user_enrollment = enrollment
        if instance not in course_instances:  # Avoid duplicates
            enrolled_instances.append(instance)
    
    # Calculate stats for enrolled instances (after they're created)
    for instance in enrolled_instances:
        enrollments = instance.enrollments.all()
        if enrollments:
            total_progress = sum(e.course_progress.overall_progress for e in enrollments)
            total_score = sum(e.course_progress.overall_score for e in enrollments)
            instance.avg_progress = total_progress / len(enrollments)
            instance.avg_score = total_score / len(enrollments)
        else:
            instance.avg_progress = 0
            instance.avg_score = 0
    
    # Fetch KnowledgeTree legacy groups for instructors (with MasteryGrids node IDs)
    legacy_groups = []
    if request.user.kt_login or request.user.kt_user_id:
        try:
            from .kt_utils import get_user_groups_with_masterygrids_nodes
            legacy_groups = get_user_groups_with_masterygrids_nodes(request.user)
            logger.info(f"Found {len(legacy_groups)} legacy groups for instructor {request.user.username}")
        except Exception as e:
            logger.warning(f"Failed to fetch legacy groups for instructor {request.user.username}: {str(e)}")
            legacy_groups = []
    
    return render(request, 'dashboard/instructor_dashboard.html', {
        'courses': courses,
        'course_instances': course_instances,
        'enrolled_instances': enrolled_instances,
        'legacy_groups': legacy_groups
    })

@login_required
def generate_course_auth_url(request):
    """
    Generates an encrypted token for course authoring login.
    Uses stored password from database (user.course_authoring_password).
    """
    logger.info("=" * 80)
    logger.info(f"generate_course_auth_url called for user: {request.user.email}")
    logger.info(f"User ID: {request.user.id}")
    logger.info(f"User Full Name: {request.user.full_name}")
    logger.info(f"Stored Password (first 16 chars): {request.user.course_authoring_password[:16] if request.user.course_authoring_password else 'None'}...")
    logger.info(f"Request Method: {request.method}")
    logger.info(f"Request Path: {request.path}")
    logger.info("-" * 80)
    
    try:
        # Use stored password from database
        # If password doesn't exist, it will be generated and stored
        token = get_course_auth_token(request.user, retry_on_mismatch=True)
        
        logger.info(f"Successfully generated token for user {request.user.email}")
        logger.info("=" * 80)
        return JsonResponse({"token": token})
    except ValueError as e:
        logger.error("=" * 80)
        logger.error(f"ValueError in generate_course_auth_url: {e}")
        logger.error(f"User: {request.user.email}")
        logger.error("=" * 80)
        return JsonResponse({"error": str(e)}, status=401)
    except requests.exceptions.HTTPError as e:
        # Handle specific HTTP errors (like 422 for password mismatch)
        error_message = str(e)
        status_code = e.response.status_code if e.response else 500
        
        logger.error("=" * 80)
        logger.error(f"HTTPError in generate_course_auth_url")
        logger.error(f"Status Code: {status_code}")
        logger.error(f"User: {request.user.email}")
        
        # Check if it's a password mismatch error
        is_password_mismatch = (
            status_code == 422 and 
            ("PASSWORD_MISMATCH" in error_message or "password doesn't match" in error_message.lower() or "Invalid email or password" in error_message)
        )
        
        # Extract more specific error message if available
        if e.response:
            try:
                error_data = e.response.json()
                error_message = error_data.get('message', error_message)
                logger.error(f"Error Response (JSON): {json.dumps(error_data, indent=2)}")
            except (ValueError, KeyError):
                logger.error(f"Error Response (Text): {e.response.text[:500]}")
        
        logger.error(f"Error Message: {error_message}")
        logger.error(f"Is Password Mismatch: {is_password_mismatch}")
        logger.error("=" * 80)
        
        response_data = {
            "error": error_message,
            "status_code": status_code
        }
        
        # Add helpful information for password mismatches
        if is_password_mismatch:
            response_data["password_mismatch"] = True
            response_data["suggestion"] = (
                "Your account exists in course-authoring with a different password. "
                "The system has attempted to reset your password and retry. "
                "If this error persists, you may need to contact support to sync your password in course-authoring."
            )
        
        return JsonResponse(response_data, status=status_code)
    except requests.exceptions.RequestException as e:
        logger.error("=" * 80)
        logger.error(f"RequestException in generate_course_auth_url: {e}")
        logger.error(f"User: {request.user.email}")
        logger.error(f"Exception Type: {type(e).__name__}")
        logger.error("=" * 80)
        return JsonResponse({
            "error": f"Failed to connect to course-authoring service: {str(e)}"
        }, status=500)
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"Unexpected error in generate_course_auth_url: {e}")
        logger.error(f"User: {request.user.email}")
        logger.error(f"Exception Type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        logger.error("=" * 80)
        return JsonResponse({
            "error": f"An unexpected error occurred: {str(e)}"
        }, status=500)


@login_required
def proxy_course_authoring_x_login(request):
    """
    Proxies the x-login request to course-authoring to avoid CORS issues.
    The token is sent from the frontend, and we forward it to course-authoring.
    """
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    try:
        import json
        data = json.loads(request.body)
        token = data.get('token')
        
        if not token:
            return JsonResponse({"error": "Token is required"}, status=400)
        
        logger.info("=" * 80)
        logger.info(f"PROXY X-LOGIN REQUEST for user: {request.user.email}")
        logger.info(f"Token (first 50 chars): {token[:50] if token else 'None'}...")
        logger.info("-" * 80)
        
        # Forward the request to course-authoring
        response = requests.post(
            "https://proxy.personalized-learning.org/next.course-authoring/api/auth/x-login",
            json={"token": token},
            timeout=10,
            allow_redirects=False
        )
        
        # Log the response
        logger.info(f"X-Login Response Status: {response.status_code}")
        logger.info(f"X-Login Response Headers: {dict(response.headers)}")
        
        try:
            response_data = response.json()
            logger.info(f"X-Login Response Body: {json.dumps(response_data, indent=2)}")
        except:
            logger.info(f"X-Login Response Body (Text): {response.text[:200]}...")
        
        logger.info("=" * 80)
        
        # Forward the response to the client
        if response.status_code == 200:
            return JsonResponse(response.json(), status=200)
        else:
            # Forward error response
            try:
                error_data = response.json()
                return JsonResponse(error_data, status=response.status_code)
            except:
                return JsonResponse(
                    {"error": response.text or "Unknown error"},
                    status=response.status_code
                )
                
    except Exception as e:
        logger.error(f"Error proxying x-login request: {e}", exc_info=True)
        return JsonResponse({
            "error": f"Failed to proxy request: {str(e)}"
        }, status=500)


@login_required
def reset_course_authoring_password_view(request):
    """
    API endpoint to reset the course-authoring password for the current user.
    Returns the new password that needs to be set in course-authoring.
    """
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    try:
        new_password = reset_course_authoring_password(request.user)
        logger.info(f"User {request.user.email} reset their course-authoring password")
        return JsonResponse({
            "success": True,
            "new_password": new_password,
            "message": (
                f"Password reset successful. Your new password is: {new_password}\n\n"
                f"Please contact the course-authoring administrator (Mohammad Hassany) "
                f"to set this password for your account in course-authoring. "
                f"Once set, you'll be able to authenticate successfully."
            )
        })
    except Exception as e:
        logger.error(f"Error resetting course-authoring password for user {request.user.email}: {e}", exc_info=True)
        return JsonResponse({
            "error": f"Failed to reset password: {str(e)}"
        }, status=500)

@login_required
def legacy_dashboard(request):
    """
    Displays the legacy dashboard with learning analytics for MasteryGrids courses.
    Accepts ?grp=GROUP_ID GET parameter to auto-populate and fetch data.
    """
    # Get Group ID from GET parameter if provided
    preselected_group = request.GET.get('grp', '').strip()
    
    # Try to get user's KnowledgeTree groups and Course IDs automatically
    auto_groups = []
    if request.user.kt_login or request.user.kt_user_id:
        try:
            auto_groups = get_user_groups_with_course_ids(request.user)
            logger.info(f"Found {len(auto_groups)} groups for user {request.user.username}")
        except Exception as e:
            logger.warning(f"Failed to auto-discover groups for user {request.user.username}: {str(e)}")
            auto_groups = []
    
    return render(request, 'dashboard/legacy_dashboard.html', {
        'user': request.user,
        'auto_groups': auto_groups,  # Pass groups to template (will be serialized with json_script filter)
        'preselected_group': preselected_group,  # Group ID from GET parameter
    })

@login_required
def discover_course_ids(request):
    """
    API endpoint to discover Course IDs for a selected group.
    Called on-demand when user selects a group from the dropdown.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        group_login = request.GET.get('grp', '').strip()
        if not group_login:
            return JsonResponse({
                'error': 'Group login (grp) parameter required'
            }, status=400)
        
        if not (request.user.kt_login or request.user.kt_user_id):
            return JsonResponse({
                'error': 'User is not linked to a KnowledgeTree account'
            }, status=404)
        
        # Use direct database query instead of API discovery
        from .kt_utils import get_course_ids_from_aggregate_db
        course_id_mappings = get_course_ids_from_aggregate_db([group_login])
        course_ids = course_id_mappings.get(group_login, [])
        
        return JsonResponse({
            'success': True,
            'group_login': group_login,
            'course_ids': course_ids
        })
    except Exception as e:
        logger.error(f"Error discovering Course IDs: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': f'Failed to discover Course IDs: {str(e)}',
            'course_ids': []
        }, status=500)


@login_required
def get_course_resources_api(request, group_login: str):
    """
    API endpoint to get course resources for a KnowledgeTree group.
    
    Returns JSON with list of resources (MasteryGrids, surveys, etc.) that can be
    rendered in an IFrame using the Show servlet.
    
    URLs include required KnowledgeTree parameters (usr, grp, sid, cid) as per
    KnowledgeTree content serving requirements.
    
    If user doesn't have a KnowledgeTree session, returns a flag indicating
    that authentication is required (Option B: redirect to KT login).
    """
    try:
        # Get user login (use kt_login if available, otherwise username)
        user_login = request.user.kt_login or request.user.username
        
        # Get session ID (Django session key)
        session_id = request.session.session_key
        
        # Get course resources with required parameters
        resources = get_course_resources(
            group_login=group_login,
            user_login=user_login,
            session_id=session_id,
            course_id=None  # Will be fetched from aggregate DB
        )
        
        # Check if user has KnowledgeTree session
        # Note: /PortalServices/Auth is stateless and does not create HTTP sessions
        # Users need to authenticate via browser (redirect to KT login) to get JSESSIONID cookie
        # This is the recommended approach for accessing protected resources
        has_session = has_kt_session(request)
        
        response_data = {
            'success': True,
            'resources': resources,
            'group_login': group_login,
            'count': len(resources),
            'has_kt_session': has_session,
            'kt_session_required': not has_session,
            'kt_login_url': get_kt_login_url() if not has_session else None
        }
        
        if not has_session:
            logger.info(f"User {request.user.username} does not have KnowledgeTree HTTP session")
            logger.info(f"Resource access will require redirect to KnowledgeTree login (browser-based authentication)")
            logger.info(f"This is expected - /PortalServices/Auth is stateless and does not create sessions")
        
        return JsonResponse(response_data)
    except Exception as e:
        logger.error(f"Error in get_course_resources_api for group {group_login}: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'resources': [],
            'group_login': group_login
        }, status=500)

@login_required
def fetch_class_list(request):
    """
    Fetch the class list using direct database query.
    Replaces GetClassList API call for better performance.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        # Get group login from request
        group_login = request.GET.get('grp', '').strip()
        
        if not group_login:
            return JsonResponse({
                'error': 'Group ID (grp) parameter is required'
            }, status=400)
        
        logger.info(f"Fetching class list for group: {group_login}")
        
        # Use direct database query
        from .db_queries import get_class_list_from_db
        data = get_class_list_from_db(group_login)
        
        if not data or not data.get('learners'):
            logger.warning(f"No learners found for group: {group_login}")
            return JsonResponse({
                'learners': [],
                'groupName': group_login,
                'error': 'No students found for this group'
            })
        
        logger.info(f"Successfully fetched {len(data['learners'])} learners for group {group_login}")
        return JsonResponse(data)
        
    except Exception as e:
        logger.error(f"Error in fetch_class_list: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': f'An unexpected error occurred: {str(e)}',
            'learners': [],
            'groupName': request.GET.get('grp', '')
        }, status=500)

@login_required
def fetch_analytics_data(request):
    """
    Fetch analytics data using direct database queries.
    Replaces GetContentLevels API call for better performance.
    
    Note: This endpoint is called per-student by the frontend.
    For efficiency, we fetch course structure once and student progress.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        # Get parameters from request
        learner_id = request.GET.get('usr', '').strip()
        group_login = request.GET.get('grp', '').strip()
        course_id_str = request.GET.get('cid', '').strip()
        
        if not group_login or not course_id_str:
            return JsonResponse({
                'error': 'Group ID (grp) and Course ID (cid) are required'
            }, status=400)
        
        try:
            course_id = int(course_id_str)
        except ValueError:
            return JsonResponse({
                'error': f'Invalid Course ID: {course_id_str}'
            }, status=400)
        
        logger.info(f"Fetching analytics for learner: {learner_id}, group: {group_login}, course: {course_id}")
        
        # Import database query functions
        from .db_queries import (
            get_course_structure_from_db,
            get_student_progress_from_db,
            get_class_list_from_db
        )
        
        # Get class list (for learner info and group name)
        class_list_data = get_class_list_from_db(group_login)
        if not class_list_data or not class_list_data.get('learners'):
            return JsonResponse({
                'error': f'No students found for group: {group_login}',
                'learners': [],
                'topics': []
            }, status=404)
        
        # Get course structure
        course_structure = get_course_structure_from_db(group_login, course_id)
        if not course_structure:
            return JsonResponse({
                'error': f'Course structure not found for group: {group_login}, course: {course_id}',
                'learners': [],
                'topics': []
            }, status=404)
        
        # Get resource names for parsing
        resource_names = [r['id'] for r in resources] if resources else None
        
        # Get student progress
        progress_data = get_student_progress_from_db(learner_id, course_id, resource_names=resource_names) if learner_id else None
        
        # Build response for single student (matching API format)
        topics = course_structure.get('topics', [])
        resources = course_structure.get('resources', [])
        
        # Build learner state
        learner_state = {
            'topics': {},
            'activities': {}
        }
        
        if progress_data:
            topics_data = progress_data.get('topics', {})
            content_data = progress_data.get('content', {})  # Activity-level progress
            
            for topic in topics:
                topic_name = topic['id']
                topic_progress = topics_data.get(topic_name, {})
                
                learner_state['topics'][topic_name] = {
                    'values': {},
                    'overall': topic_progress.get('overall', {'k': 0.0, 'p': 0.0})
                }
                
                # Populate resource values
                for resource in resources:
                    resource_name = resource['id']
                    resource_values = topic_progress.get('values', {}).get(resource_name, {'k': 0.0, 'p': 0.0})
                    learner_state['topics'][topic_name]['values'][resource_name] = resource_values
                
                # Build activities structure with progress data (object keyed by activity IDs)
                learner_state['activities'][topic_name] = {}
                for resource_name, activities in topic.get('activities', {}).items():
                    # Convert array to object keyed by activity ID, including progress
                    activities_obj = {}
                    for activity in activities:
                        activity_id = activity['id']
                        # Get activity progress from content_data (keyed by content_name/activity_id)
                        activity_progress = content_data.get(activity_id, {'k': 0.0, 'p': 0.0})
                        activities_obj[activity_id] = {
                            'id': activity_id,
                            'name': activity['name'],
                            'url': activity.get('url', ''),
                            'values': {
                                'k': activity_progress.get('k', 0.0),
                                'p': activity_progress.get('p', 0.0)
                            }
                        }
                    learner_state['activities'][topic_name][resource_name] = activities_obj
        else:
            # No progress data - initialize empty structure
            for topic in topics:
                topic_name = topic['id']
                learner_state['topics'][topic_name] = {
                    'values': {r['id']: {'k': 0.0, 'p': 0.0} for r in resources},
                    'overall': {'k': 0.0, 'p': 0.0}
                }
                learner_state['activities'][topic_name] = {
                    r['id']: {} for r in resources
                }
        
        # Find learner info
        learner_info = next(
            (l for l in class_list_data['learners'] if l['learnerId'] == learner_id),
            {'learnerId': learner_id, 'name': learner_id, 'email': ''}
        )
        
        # Build response matching API format
        response_data = {
            'learners': [{
                'id': learner_id,
                'name': learner_info.get('name', learner_id),
                'email': learner_info.get('email', ''),
                'isHidden': False,
                'state': learner_state
            }],
            'topics': topics,
            'resources': resources,
            'context': {
                'group': {
                    'name': class_list_data.get('groupName', group_login)
                },
                'learnerId': learner_id,
                'course_id': course_id,
                'course_name': course_structure.get('course_name', ''),
                'domain': course_structure.get('domain', '')
            }
        }
        
        logger.info(f"Successfully built analytics response for learner {learner_id}")
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Error in fetch_analytics_data: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': f'An unexpected error occurred: {str(e)}',
            'learners': [],
            'topics': []
        }, status=500)

@login_required
def fetch_all_students_analytics(request):
    """
    Batch fetch analytics data for ALL students in a course.
    This replaces the per-student fetching approach for much better performance.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        # Get parameters from request
        group_login = request.GET.get('grp', '').strip()
        course_id_str = request.GET.get('cid', '').strip()
        
        if not group_login or not course_id_str:
            return JsonResponse({
                'error': 'Group ID (grp) and Course ID (cid) are required'
            }, status=400)
        
        try:
            course_id = int(course_id_str)
        except ValueError:
            return JsonResponse({
                'error': f'Invalid Course ID: {course_id_str}'
            }, status=400)
        
        logger.info(f"Batch fetching analytics for group: {group_login}, course: {course_id}")
        
        # Import batch fetch function
        from .db_queries import fetch_all_students_analytics
        
        # Fetch all students' data in one go
        response_data = fetch_all_students_analytics(group_login, course_id)
        
        if not response_data.get('learners'):
            return JsonResponse({
                'error': f'No data found for group: {group_login}, course: {course_id}',
                'learners': [],
                'topics': []
            }, status=404)
        
        logger.info(f"Successfully fetched analytics for {len(response_data['learners'])} students")
        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error in fetch_all_students_analytics: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': f'An unexpected error occurred: {str(e)}',
            'learners': [],
            'topics': []
        }, status=500)