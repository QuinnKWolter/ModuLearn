from django.shortcuts import render, redirect
from courses.models import Enrollment, Course, CourseInstance
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import requests
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from courses.utils import get_course_auth_token, reset_course_authoring_password
from courses.demo_courses import create_demo_course_for_key
import json
from urllib.parse import urlparse
from .kt_utils import get_course_resources, get_user_groups_with_course_ids, has_kt_session, get_kt_login_url
import logging
from modulearn.learning.selectors.dashboard import (
    build_instructor_dashboard_context,
    build_student_dashboard_context,
)
from modulearn.learning.selectors.timelines import get_course_instance_recent_activity
from modulearn.integrations.course_authoring import build_x_login_url
from modulearn.core.roles import (
    get_legacy_course_groups,
    get_legacy_masterygrids_groups,
    get_user_role_snapshot,
)
from recruitment.services.participants import participant_course_redirect

logger = logging.getLogger(__name__)

@login_required
def student_dashboard(request):
    """
    Displays the student's dashboard with enrolled courses.
    """
    redirect_response = participant_course_redirect(request.user)
    if redirect_response:
        return redirect_response

    role_snapshot = get_user_role_snapshot(request.user)
    if role_snapshot["effective_is_instructor"]:
        return redirect('dashboard:instructor_dashboard')
    return render(request, 'dashboard/student_dashboard.html', build_student_dashboard_context(request.user))

@login_required
def instructor_dashboard(request):
    """
    Displays the instructor's dashboard with their courses and course sessions.
    """
    redirect_response = participant_course_redirect(request.user)
    if redirect_response:
        return redirect_response

    if not get_user_role_snapshot(request.user)["effective_is_instructor"]:
        return redirect('dashboard:student_dashboard')
    return render(request, 'dashboard/instructor_dashboard.html', build_instructor_dashboard_context(request.user))


@login_required
@require_POST
def create_demo_course(request):
    if not get_user_role_snapshot(request.user)["effective_is_instructor"]:
        messages.error(request, "Only instructors can create demo courses.")
        return redirect('dashboard:student_dashboard')

    try:
        demo_key = (request.POST.get("demo_type") or "").strip()
        _course, instance = create_demo_course_for_key(request.user, demo_key)
    except ValueError as error:
        messages.error(request, str(error))
        return redirect('dashboard:instructor_dashboard')
    except Exception:
        logger.exception("Failed to create demo course for user %s", request.user.id)
        messages.error(request, "The demo course could not be created. Please try again.")
        return redirect('dashboard:instructor_dashboard')

    messages.success(request, "Demo course created. You can review and configure it here.")
    return redirect('courses:course_configuration', instance_id=instance.id)


@login_required
def modulearn_analytics_dashboard(request):
    """
    ModuLearn-native analytics dashboard (non-legacy).
    Reuses the legacy dashboard KPI/grid templates, but sources data from ORM models.
    """
    redirect_response = participant_course_redirect(request.user)
    if redirect_response:
        return redirect_response

    if not get_user_role_snapshot(request.user)["effective_is_instructor"]:
        return redirect('dashboard:student_dashboard')

    preselected_instance_id = (request.GET.get('instance_id') or '').strip()

    instances_qs = CourseInstance.objects.filter(
        instructors=request.user
    ).select_related('course').order_by('-created_at')

    # Provide lightweight JSON for dropdown (avoid serializing full model)
    course_instances = [{
        'id': str(ci.id),
        'label': f"{ci.course.title if ci.course else 'Untitled Course'} — {ci.group_name or 'Session'}",
    } for ci in instances_qs]

    return render(request, 'dashboard/modulearn_analytics_dashboard.html', {
        'course_instances': course_instances,
        'preselected_instance_id': preselected_instance_id,
    })


@login_required
def fetch_modulearn_instance_analytics(request):
    """
    API endpoint: return a legacy-shaped analytics response for a ModuLearn CourseInstance.
    Query param: ?instance_id=<CourseInstance.id>
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    instance_id = (request.GET.get('instance_id') or '').strip()
    if not instance_id:
        return JsonResponse({'error': 'instance_id is required'}, status=400)

    if not get_user_role_snapshot(request.user)["effective_is_instructor"]:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    try:
        from courses.models import Unit, Module, ModuleProgress
        from recruitment.models import ParticipantSession

        course_instance = CourseInstance.objects.select_related('course').get(id=instance_id)
        if not course_instance.instructors.filter(id=request.user.id).exists():
            return JsonResponse({'error': 'Not found'}, status=404)

        # Include all enrollments for the instance (some may be inactive, but analytics should not silently drop them)
        enrollments = Enrollment.objects.filter(
            course_instance=course_instance,
        ).select_related('student')

        course = course_instance.course
        units = list(Unit.objects.filter(course=course).order_by('id'))
        modules = list(Module.objects.filter(unit__in=units).select_related('unit').order_by('id'))

        def _module_type_key(m):
            # Best-effort bucketing for "module type" columns.
            # Prefer platform_name (human-facing), then provider_id, otherwise a fallback.
            key = (getattr(m, 'platform_name', '') or '').strip()
            if key:
                return key
            key = (getattr(m, 'provider_id', '') or '').strip()
            if key:
                return key
            # Try JSON content_data if present
            try:
                cd = getattr(m, 'content_data', None) or {}
                if isinstance(cd, dict):
                    t = (cd.get('type') or cd.get('module_type') or cd.get('kind') or '').strip()
                    if t:
                        return t
            except Exception:
                pass
            return 'Modules'

        # Determine module types (these become "resource columns")
        type_keys = []
        for m in modules:
            k = _module_type_key(m)
            if k not in type_keys:
                type_keys.append(k)

        resources = [
            {'id': f"type::{k}", 'name': k}
            for k in type_keys
        ]

        # Precompute modules per unit and per type for efficient aggregation
        modules_by_unit = {}
        modules_by_unit_and_type = {}
        for m in modules:
            modules_by_unit.setdefault(m.unit_id, []).append(m)
            k = _module_type_key(m)
            modules_by_unit_and_type.setdefault((m.unit_id, k), []).append(m)

        topics = [{
            'id': str(u.id),
            'name': u.title,
            'order': idx + 1,
            'activities': {
                # Keyed by resource id (type::<key>)
                **{
                    f"type::{k}": [
                        {'id': str(m.id), 'name': m.title, 'url': m.content_url or ''}
                        for m in modules_by_unit_and_type.get((u.id, k), [])
                    ]
                    for k in type_keys
                }
            }
        } for idx, u in enumerate(units)]

        enrollment_ids = [e.id for e in enrollments]
        module_ids = [m.id for m in modules]
        sessions_by_enrollment = {
            session.enrollment_id: session
            for session in ParticipantSession.objects.filter(enrollment_id__in=enrollment_ids)
            .select_related('recruitment_source')
            .order_by('-entered_at')
        }

        progress_qs = ModuleProgress.objects.filter(
            enrollment_id__in=enrollment_ids,
            module_id__in=module_ids,
        ).values('enrollment_id', 'module_id', 'progress', 'score')

        progress_by_enrollment = {}
        for row in progress_qs:
            progress_by_enrollment.setdefault(row['enrollment_id'], {})[row['module_id']] = row

        learners = []
        for e in enrollments:
            per_topic = {}
            per_activities = {}
            module_progress_map = progress_by_enrollment.get(e.id, {})

            for u in units:
                topic_values = {}
                all_ps = []

                for k in type_keys:
                    type_modules = modules_by_unit_and_type.get((u.id, k), [])
                    if type_modules:
                        ps = []
                        for m in type_modules:
                            mp = module_progress_map.get(m.id)
                            ps.append(float(mp.get('progress') or 0.0) if mp else 0.0)
                        avg_p = sum(ps) / len(ps)
                        all_ps.extend(ps)
                    else:
                        avg_p = 0.0

                    topic_values[f"type::{k}"] = {'k': 0.0, 'p': avg_p}

                overall_p = (sum(all_ps) / len(all_ps)) if all_ps else 0.0

                per_topic[str(u.id)] = {
                    'values': topic_values,
                    'overall': {'k': 0.0, 'p': overall_p}
                }

                per_activities[str(u.id)] = {}
                for k in type_keys:
                    res_id = f"type::{k}"
                    per_activities[str(u.id)][res_id] = {}
                    for m in modules_by_unit_and_type.get((u.id, k), []):
                        mp = module_progress_map.get(m.id) or {}
                        p = float(mp.get('progress') or 0.0) if mp else 0.0
                        score = mp.get('score')
                        kk = (float(score) / 100.0) if score is not None else 0.0
                        per_activities[str(u.id)][res_id][str(m.id)] = {
                            'id': str(m.id),
                            'name': m.title,
                            'url': m.content_url or '',
                            'values': {'k': kk, 'p': p}
                        }

            participant_session = sessions_by_enrollment.get(e.id)
            learners.append({
                'id': e.student.username,
                'name': getattr(e.student, 'full_name', '') or e.student.username,
                'email': getattr(e.student, 'email', '') or '',
                'condition': getattr(participant_session, 'condition', '') or '',
                'participant_session_uuid': str(participant_session.uuid) if participant_session else '',
                'recruitment_platform': participant_session.recruitment_source.platform if participant_session else '',
                'isHidden': False,
                'state': {
                    'topics': per_topic,
                    'activities': per_activities,
                }
            })

        def _average_topics_for_learners(selected_learners):
            avg_topics = {}
            for unit in units:
                values = {}
                overall_vals = []
                for resource in resources:
                    rid = resource['id']
                    if selected_learners:
                        vals = [learner['state']['topics'][str(unit.id)]['values'].get(rid, {}).get('p', 0.0) for learner in selected_learners]
                        avg_p = sum(vals) / len(vals)
                    else:
                        avg_p = 0.0
                    values[rid] = {'k': 0.0, 'p': avg_p}
                    overall_vals.append(avg_p)
                overall_p = (sum(overall_vals) / len(overall_vals)) if overall_vals else 0.0
                avg_topics[str(unit.id)] = {
                    'values': values,
                    'overall': {'k': 0.0, 'p': overall_p},
                }
            return avg_topics

        # Class and condition averages
        class_avg_topics = _average_topics_for_learners(learners)
        condition_names = sorted({learner.get('condition') for learner in learners if learner.get('condition')})
        condition_groups = [
            {
                'name': f"Condition: {condition}",
                'condition': condition,
                'state': {'topics': _average_topics_for_learners([learner for learner in learners if learner.get('condition') == condition])},
            }
            for condition in condition_names
        ]

        response_data = {
            'learners': learners,
            'topics': topics,
            'resources': resources,
            'recent_events': get_course_instance_recent_activity(course_instance, limit=12),
            'groups': [{
                'name': 'Class Average',
                'state': {'topics': class_avg_topics}
            }, *condition_groups],
            'context': {
                'group': {
                    'name': f"{course.title if course else 'Course'} — {course_instance.group_name or 'Session'}"
                },
                'learnerId': None,
                'course_instance_id': str(course_instance.id),
                'course_id': str(course.id) if course else None,
                'course_name': course.title if course else '',
                'domain': 'modulearn',
                'condition_counts': {condition: len([learner for learner in learners if learner.get('condition') == condition]) for condition in condition_names},
            }
        }

        return JsonResponse(response_data)
    except CourseInstance.DoesNotExist:
        return JsonResponse({'error': 'Course session not found'}, status=404)
    except Exception as e:
        logger.error(f"Error building ModuLearn analytics: {str(e)}", exc_info=True)
        return JsonResponse({'error': f'An unexpected error occurred: {str(e)}'}, status=500)

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
            build_x_login_url(),
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
    Accepts ?grp=GROUP_ID&cid=COURSE_ID GET parameters to auto-populate and fetch data.
    """
    preselected_group = request.GET.get('grp', '').strip()
    preselected_course = request.GET.get('cid', '').strip()

    return render(request, 'dashboard/legacy_dashboard.html', {
        'user': request.user,
        'auto_groups': [],
        'preselected_group': preselected_group,
        'preselected_course': preselected_course,
    })


@login_required
def get_legacy_groups_api(request):
    """
    Lazily fetch legacy group data for dashboard hydration.

    Query param:
    - variant=courses|masterygrids
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    variant = (request.GET.get('variant') or 'courses').strip().lower()

    try:
        if variant == 'masterygrids':
            groups = get_legacy_masterygrids_groups(request.user)
        else:
            groups = get_legacy_course_groups(request.user)

        return JsonResponse({
            'success': True,
            'variant': variant,
            'count': len(groups),
            'groups': groups,
        })
    except Exception as e:
        logger.error(f"Error loading legacy groups for variant={variant}: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'variant': variant,
            'groups': [],
            'error': f'Failed to load legacy groups: {str(e)}',
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
        
        topics = course_structure.get('topics', [])
        resources = course_structure.get('resources', [])

        # Get resource names for parsing
        resource_names = [resource['id'] for resource in resources] if resources else None
        
        # Get student progress
        progress_data = get_student_progress_from_db(learner_id, course_id, resource_names=resource_names) if learner_id else None
        
        # Build response for single student (matching API format)
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
                                'p': activity_progress.get('p', 0.0),
                                **{
                                    key: activity_progress.get(key)
                                    for key in ('a', 's', 'aSeq')
                                    if activity_progress.get(key) not in (None, '')
                                }
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
                'lastActive': progress_data.get('last_update') if progress_data else None,
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
