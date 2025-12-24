from django.shortcuts import render, redirect
from courses.models import Enrollment, Course, CourseInstance
from django.contrib.auth.decorators import login_required
import requests
from django.http import JsonResponse
from courses.utils import get_course_auth_token
import json
from urllib.parse import urlparse
from py_mini_racer import MiniRacer
from .kt_utils import get_user_groups_with_course_ids
from .db_query_interface import DatabaseQueryInterface
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
    # Try to get user's KnowledgeTree groups and Course IDs automatically
    auto_groups = []
    if request.user.kt_login or request.user.kt_user_id:
        try:
            auto_groups = get_user_groups_with_course_ids(request.user)
            logger.info(f"Found {len(auto_groups)} groups for user {request.user.username}")
        except Exception as e:
            logger.warning(f"Failed to auto-discover groups for user {request.user.username}: {str(e)}")
            auto_groups = []
    
    return render(request, 'dashboard/mockup_dashboard.html', {
        'user': request.user,
        'auto_groups': auto_groups,  # Pass groups to template
    })


@login_required
def fetch_user_groups(request):
    """
    API endpoint to fetch user's KnowledgeTree groups (without Course IDs).
    Used by JavaScript to show group dropdown.
    Course IDs are discovered on-demand when a group is selected.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        if not (request.user.kt_login or request.user.kt_user_id):
            return JsonResponse({
                'error': 'User is not linked to a KnowledgeTree account',
                'groups': []
            }, status=404)
        
        groups = get_user_groups_with_course_ids(request.user)
        
        return JsonResponse({
            'success': True,
            'groups': groups
        })
    except Exception as e:
        logger.error(f"Error fetching user groups: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': f'Failed to fetch groups: {str(e)}',
            'groups': []
        }, status=500)


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
def db_query_interface(request):
    """
    Database query interface for testing and exploring MySQL databases.
    Allows entering credentials and running SELECT queries.
    
    WARNING: This is a testing tool. Restrict access in production!
    """
    if request.method == 'POST':
        action = request.POST.get('action', '')
        
        if action == 'connect':
            # Get connection parameters
            host = request.POST.get('host', '').strip()
            port = int(request.POST.get('port', 3306))
            user = request.POST.get('user', '').strip()
            password = request.POST.get('password', '').strip()
            database = request.POST.get('database', '').strip()
            
            # Get SSH tunnel parameters
            use_ssh = request.POST.get('use_ssh') == 'on'
            ssh_host = request.POST.get('ssh_host', '').strip() if use_ssh else None
            ssh_port = int(request.POST.get('ssh_port', 22)) if use_ssh else 22
            ssh_user = request.POST.get('ssh_user', '').strip() if use_ssh else None
            ssh_auth_method = request.POST.get('ssh_auth_method', 'password') if use_ssh else None
            ssh_password = request.POST.get('ssh_password', '').strip() if use_ssh and ssh_auth_method == 'password' else None
            ssh_key_path = request.POST.get('ssh_key_path', '').strip() if use_ssh and ssh_auth_method == 'key' else None
            
            if not all([host, user, password, database]):
                return JsonResponse({
                    'success': False,
                    'message': 'All database connection fields are required'
                })
            
            if use_ssh:
                if not ssh_host or not ssh_user:
                    return JsonResponse({
                        'success': False,
                        'message': 'SSH host and username are required when using SSH tunnel'
                    })
                if ssh_auth_method == 'password' and not ssh_password:
                    return JsonResponse({
                        'success': False,
                        'message': 'SSH password is required when using password authentication'
                    })
                if ssh_auth_method == 'key' and not ssh_key_path:
                    return JsonResponse({
                        'success': False,
                        'message': 'SSH key path is required when using key authentication'
                    })
            
            # Create database interface
            db_interface = DatabaseQueryInterface(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                ssh_host=ssh_host,
                ssh_port=ssh_port,
                ssh_user=ssh_user,
                ssh_password=ssh_password,
                ssh_key_path=ssh_key_path
            )
            
            success, message = db_interface.connect()
            
            if success:
                # Store connection info in session (passwords stored temporarily - not ideal but for testing)
                request.session['db_test_connection'] = {
                    'host': host,
                    'port': port,
                    'user': user,
                    'password': password,
                    'database': database,
                    'use_ssh': use_ssh,
                    'ssh_host': ssh_host,
                    'ssh_port': ssh_port,
                    'ssh_user': ssh_user,
                    'ssh_password': ssh_password,
                    'ssh_key_path': ssh_key_path
                }
                return JsonResponse({
                    'success': True,
                    'message': message
                })
            else:
                # Clean up on failure
                db_interface.disconnect()
                return JsonResponse({
                    'success': False,
                    'message': message
                })
        
        elif action == 'disconnect':
            # Clear session
            if 'db_test_connection' in request.session:
                del request.session['db_test_connection']
            return JsonResponse({'success': True, 'message': 'Disconnected'})
        
        elif action == 'query':
            # Execute SQL query
            if 'db_test_connection' not in request.session:
                return JsonResponse({
                    'success': False,
                    'message': 'Not connected. Please connect first.'
                })
            
            query = request.POST.get('query', '').strip()
            max_rows = int(request.POST.get('max_rows', 100))
            
            if not query:
                return JsonResponse({
                    'success': False,
                    'message': 'Query is required'
                })
            
            # Reconnect using session data
            conn_info = request.session['db_test_connection']
            db_interface = DatabaseQueryInterface(
                host=conn_info['host'],
                port=conn_info['port'],
                user=conn_info['user'],
                password=conn_info['password'],
                database=conn_info['database'],
                ssh_host=conn_info.get('ssh_host'),
                ssh_port=conn_info.get('ssh_port', 22),
                ssh_user=conn_info.get('ssh_user'),
                ssh_password=conn_info.get('ssh_password'),
                ssh_key_path=conn_info.get('ssh_key_path')
            )
            
            success, message = db_interface.connect()
            if not success:
                return JsonResponse({
                    'success': False,
                    'message': f'Reconnection failed: {message}'
                })
            
            try:
                success, results, message, row_count = db_interface.execute_query(query, max_rows)
                return JsonResponse({
                    'success': success,
                    'results': results,
                    'message': message,
                    'row_count': row_count
                })
            finally:
                db_interface.disconnect()
        
        elif action == 'SHOW TABLES':
            # Quick action: Show tables
            if 'db_test_connection' not in request.session:
                return JsonResponse({
                    'success': False,
                    'message': 'Not connected. Please connect first.'
                })
            
            conn_info = request.session['db_test_connection']
            db_interface = DatabaseQueryInterface(
                host=conn_info['host'],
                port=conn_info['port'],
                user=conn_info['user'],
                password=conn_info['password'],
                database=conn_info['database'],
                ssh_host=conn_info.get('ssh_host'),
                ssh_port=conn_info.get('ssh_port', 22),
                ssh_user=conn_info.get('ssh_user'),
                ssh_password=conn_info.get('ssh_password'),
                ssh_key_path=conn_info.get('ssh_key_path')
            )
            
            success, message = db_interface.connect()
            if not success:
                return JsonResponse({
                    'success': False,
                    'message': f'Reconnection failed: {message}'
                })
            
            try:
                success, tables, message = db_interface.get_tables()
                if success:
                    # Convert to list of dicts for display
                    results = [{'Tables_in_' + conn_info['database']: table} for table in tables]
                    return JsonResponse({
                        'success': True,
                        'results': results,
                        'message': message,
                        'row_count': len(results)
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': message
                    })
            finally:
                db_interface.disconnect()
        
        elif action == 'search':
            # Quick action: Search for columns/tables
            if 'db_test_connection' not in request.session:
                return JsonResponse({
                    'success': False,
                    'message': 'Not connected. Please connect first.'
                })
            
            search_term = request.POST.get('param', '').strip()
            if not search_term:
                return JsonResponse({
                    'success': False,
                    'message': 'Search term is required'
                })
            
            conn_info = request.session['db_test_connection']
            db_interface = DatabaseQueryInterface(
                host=conn_info['host'],
                port=conn_info['port'],
                user=conn_info['user'],
                password=conn_info['password'],
                database=conn_info['database'],
                ssh_host=conn_info.get('ssh_host'),
                ssh_port=conn_info.get('ssh_port', 22),
                ssh_user=conn_info.get('ssh_user'),
                ssh_password=conn_info.get('ssh_password'),
                ssh_key_path=conn_info.get('ssh_key_path')
            )
            
            success, message = db_interface.connect()
            if not success:
                return JsonResponse({
                    'success': False,
                    'message': f'Reconnection failed: {message}'
                })
            
            try:
                success, results, message = db_interface.search_tables_for_columns(search_term)
                return JsonResponse({
                    'success': success,
                    'results': results,
                    'message': message,
                    'row_count': len(results) if results else 0
                })
            finally:
                db_interface.disconnect()
    
    # GET request - show the interface
    return render(request, 'dashboard/db_query_interface.html')

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