from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Course, Module, Enrollment, Unit, StudentScore, CaliperEvent, EnrollmentCode, CourseProgress, ModuleProgress, CourseInstance
from django.contrib.auth import get_user_model
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
import json
from .utils import fetch_course_details, create_course_from_json
import logging
import traceback
from django.urls import reverse
from datetime import datetime
from django.conf import settings
import jwt
import time
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
import xml.etree.ElementTree as ET
from django.contrib.auth import login
from django.views.decorators.http import require_POST, require_GET
import os
from django.core.serializers.json import DjangoJSONEncoder
import uuid
from django.views.decorators.http import require_http_methods
from django.db.utils import IntegrityError
from django.db.models import Count
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
import requests
from django.db import models

User = get_user_model()

# Configure logging
logger = logging.getLogger(__name__)

@login_required
def course_list(request):
    """
    Displays a list of courses with enrollment and progress information.
    Instructors see courses they teach or are enrolled in.
    Students see only courses they are enrolled in.
    """
    course_instances = []
    
    if request.user.is_authenticated:
        if request.user.is_student:
            # Get only enrolled course instances for students
            enrollments = Enrollment.objects.filter(
                student=request.user
            ).select_related('course_instance', 'course_instance__course', 'course_progress')
            
            # Convert to list of course instances with attached enrollment info
            for enrollment in enrollments:
                course_instance = enrollment.course_instance
                course_instance.user_enrollment = enrollment
                course_instances.append(course_instance)
        elif request.user.is_instructor:
            # Get course instances where user is instructor
            taught_instances = CourseInstance.objects.filter(instructors=request.user)
            
            # Get enrollments where instructor is enrolled as student
            student_enrollments = Enrollment.objects.filter(
                student=request.user
            ).select_related('course_instance', 'course_instance__course', 'course_progress')
            
            # Add taught course instances
            for instance in taught_instances:
                course_instances.append(instance)
            
            # Add enrolled course instances
            for enrollment in student_enrollments:
                instance = enrollment.course_instance
                instance.user_enrollment = enrollment
                if instance not in course_instances:  # Avoid duplicates
                    course_instances.append(instance)
    
    return render(request, 'courses/course_list.html', {
        'course_instances': course_instances,
        'lti_data': getattr(request.user, 'lti_data', {})
    })

@login_required
def course_detail(request, instance_id):
    """
    Displays details of a specific course instance and related instances 
    that the user has access to.
    """
    # Get the course instance and related course
    course_instance = get_object_or_404(CourseInstance, id=instance_id)
    course = course_instance.course
    
    # Check if user is enrolled or is instructor
    is_instructor = course_instance.instructors.filter(id=request.user.id).exists()
    is_enrolled = False
    course_progress = None
    module_progress_data = {}
    
    if request.user.is_authenticated:
        # Check enrollment
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course_instance=course_instance,
            active=True
        ).first()
        
        is_enrolled = enrollment is not None
        
        if is_enrolled:
            # Get course progress
            course_progress = CourseProgress.objects.get(enrollment=enrollment)
            
            # Get all module progress for this user in this course instance
            module_progresses = ModuleProgress.objects.filter(
                enrollment=enrollment
            ).select_related('module')
            
            # Create a dictionary of module_id: progress_data
            module_progress_data = {
                mp.module.id: {
                    'is_complete': mp.progress >= 1.0,  # Consider complete if progress is 100%
                    'score': mp.score,
                    'progress': mp.progress
                } for mp in module_progresses
            }
    
    context = {
        'course': course,
        'current_instance': course_instance,
        'units': course.units.prefetch_related('modules').all(),
        'is_instructor': is_instructor,
        'is_enrolled': is_enrolled,
        'course_progress': course_progress,
        'module_progress_data': module_progress_data,
    }

    # Handle enrollment POST request
    if request.method == 'POST' and request.user.is_student:
        if not is_enrolled:
            enrollment = Enrollment.objects.create(
                student=request.user, 
                course_instance=course_instance
            )
            messages.success(request, f'You have been enrolled in {course_instance}')
            return redirect('courses:course_detail', instance_id=instance_id)

    return render(request, 'courses/course_detail.html', context)

@login_required
def module_detail(request, instance_id, unit_id, module_id):
    """
    Display details for a specific module within a course instance.
    """
    course_instance = get_object_or_404(CourseInstance, id=instance_id)
    course = course_instance.course
    
    # Check if user has access to this course instance
    if not (course_instance.instructors.filter(id=request.user.id).exists() or 
            course_instance.enrollments.filter(student=request.user).exists()):
        raise PermissionDenied("You don't have access to this course instance.")
    
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    module = get_object_or_404(Module, id=module_id, unit=unit)
    
    # Get progress for this specific instance
    progress = None
    if request.user.is_student:
        enrollment = course_instance.enrollments.get(student=request.user)
        progress = ModuleProgress.get_or_create_progress(
            user=request.user,
            module=module,
            course_instance=course_instance
        )[0]
    
    context = {
        'course': course,
        'course_instance': course_instance,
        'unit': unit,
        'module': module,
        'progress': progress,
    }

    print(context)
    
    return render(request, 'courses/module_detail.html', context)

@login_required
def unenroll(request, course_id):
    """
    Allows a user to unenroll from a course instance.
    """
    course_instance = get_object_or_404(CourseInstance, id=course_id)
    enrollment = Enrollment.objects.filter(
        student=request.user, 
        course_instance=course_instance
    ).first()

    if enrollment:
        enrollment.delete()
        messages.success(request, f'You have unenrolled from {course_instance}.')
    else:
        messages.error(request, 'You are not enrolled in this course.')

    return redirect('courses:course_detail', instance_id=course_id)

@csrf_exempt
def create_course(request):
    if not request.user.is_instructor:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body)
        course_data = data.get('course_data')

        if not course_data:
            return JsonResponse({'error': 'Course data is required'}, status=400)

        # Assuming create_course_from_json is a function that handles the course creation logic
        course = create_course_from_json(course_data, request.user)

        return JsonResponse({'success': True, 'course_id': course.id})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        logger.error(f"Error creating course: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def launch_iframe_module(request, instance_id, module_id):
    module = get_object_or_404(Module, id=module_id)
    course_instance = get_object_or_404(CourseInstance, id=instance_id)
    
    # Check if user has access to this module
    is_instructor = course_instance.instructors.filter(id=request.user.id).exists()
    is_enrolled = Enrollment.objects.filter(student=request.user, course_instance=course_instance).exists()
    
    if not (is_instructor or is_enrolled):
        return HttpResponseForbidden("You don't have access to this module")
    
    # Use the get_or_create_progress class method instead of direct get_or_create
    module_progress, created = ModuleProgress.get_or_create_progress(
        user=request.user,
        module=module,
        course_instance=course_instance
    )
    
    # Choose the best available protocol (splice > lti > pitt)
    selected_protocol = module.select_launch_protocol()
    logger.info(f"Module {module.id} '{module.title}' selected protocol: {selected_protocol}")
    print(f"DEBUG: Module {module.id} - Protocol: {selected_protocol}, Content URL: {module.content_url}")
    print(f"DEBUG: URL starts with http://: {module.content_url.startswith('http://') if module.content_url else False}")

    # Parse the URL for LTI parameters
    content_url = module.content_url
    parsed_url = urlparse(content_url)
    query_params = parse_qs(parsed_url.query)
    
    # Extract LTI launch parameters
    lti_sub = None
    if query_params.get('tool') and query_params.get('sub'):
        lti_sub = query_params['sub'][0]
    elif module.provider_id and content_url:
        # Use content_url or extract sub from it
        lti_sub = query_params.get('sub', [content_url])[0]
    
    # Handle CodeCheck URL transformation for splice protocol
    if query_params.get('tool', [''])[0] == 'codecheck' and 'sub' in query_params:
        sub_param = query_params['sub'][0]
        content_url = f'https://codecheck.me/files/wiley/{sub_param}'
    
    # Determine if we need to proxy HTTP content
    use_proxy = content_url and content_url.startswith('http://')
    print(f"DEBUG: Use proxy for HTTP content: {use_proxy}")
    
    context = {
        'module': module,
        'is_instructor': is_instructor,
        'progress': module_progress,
        'content_url': content_url,
        'state_data': module_progress.state_data if hasattr(module_progress, 'state_data') else None,
        'selected_protocol': selected_protocol,
        'course_instance': course_instance,
        'lti_sub': lti_sub,
        'use_proxy': use_proxy,
    }
    
    response = render(request, 'courses/module_frame.html', context)
    response['X-Frame-Options'] = 'SAMEORIGIN'
    return response

@login_required
def preview_iframe_module(request, module_id):
    """
    Instructor preview of a module without tracking progress or requiring an instance.
    Only accessible to instructors. Uses the module's raw content_url and never
    creates/updates ModuleProgress or CourseProgress.
    """
    module = get_object_or_404(Module, id=module_id)

    if not request.user.is_instructor:
        return HttpResponseForbidden("Preview is limited to instructors")

    # Choose the best available protocol (splice > lti > pitt)
    selected_protocol = module.select_launch_protocol()
    logger.info(f"Preview module {module.id} '{module.title}' selected protocol: {selected_protocol}")

    # Parse the URL for LTI parameters
    content_url = module.content_url
    parsed_url = urlparse(content_url)
    query_params = parse_qs(parsed_url.query)
    
    # Extract LTI launch parameters
    lti_sub = None
    if query_params.get('tool') and query_params.get('sub'):
        lti_sub = query_params['sub'][0]
    elif module.provider_id and content_url:
        # Use content_url or extract sub from it
        lti_sub = query_params.get('sub', [content_url])[0]
    
    # Handle CodeCheck URL transformation for splice protocol
    if query_params.get('tool', [''])[0] == 'codecheck' and 'sub' in query_params:
        sub_param = query_params['sub'][0]
        content_url = f'https://codecheck.me/files/wiley/{sub_param}'

    # Determine if we need to proxy HTTP content
    use_proxy = content_url and content_url.startswith('http://')
    print(f"DEBUG: Preview use proxy for HTTP content: {use_proxy}")

    context = {
        'module': module,
        'is_instructor': True,
        'progress': None,
        'content_url': content_url,
        'state_data': None,
        'preview_mode': True,
        'selected_protocol': selected_protocol,
        'lti_sub': lti_sub,
        'use_proxy': use_proxy,
    }

    response = render(request, 'courses/module_frame.html', context)
    response['X-Frame-Options'] = 'SAMEORIGIN'
    return response

@csrf_exempt
def log_lti_response(request):
    """
    Logs the response received from the LTI tool iframe.
    Handles both LTI 1.1 and 1.3 responses.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            logger.info("LTI Response Data: %s", data)
            
            # Determine LTI version from response data
            if 'id_token' in data:
                # Handle LTI 1.3 specific response data
                logger.info("Processing LTI 1.3 response")
                # Add any LTI 1.3 specific processing here
            else:
                # Handle LTI 1.1 specific response data
                logger.info("Processing LTI 1.1 response")
                # Add any LTI 1.1 specific processing here

            return JsonResponse({'success': True, 'message': 'LTI response logged successfully'})
        except Exception as e:
            logger.error(f"Error logging LTI response: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=400)

@method_decorator(csrf_exempt, name='dispatch')
class LTIOutcomesView(View):
    def post(self, request, *args, **kwargs):
        """
        Handles LTI outcomes for both 1.1 and 1.3 versions
        """
        try:
            # Check for LTI 1.3 AGS (Assignment and Grade Services)
            if 'application/vnd.ims.lis.v2.lineitem+json' in request.headers.get('Accept', ''):
                # Handle LTI 1.3 AGS request
                score_data = json.loads(request.body)
                StudentScore.objects.create(
                    user=request.user,
                    score=score_data.get('scoreGiven'),
                    result_id=score_data.get('id')
                )
            else:
                # Handle LTI 1.1 outcomes
                tree = ET.ElementTree(ET.fromstring(request.body))
                root = tree.getroot()
                lis_result_sourcedid = root.find('.//lis_result_sourcedid').text
                score = float(root.find('.//score').text)
                
                StudentScore.objects.create(
                    user=request.user,
                    lis_result_sourcedid=lis_result_sourcedid,
                    score=score
                )

            return HttpResponse(status=200)
        except Exception as e:
            logger.error(f"Error processing LTI Outcomes: {e}")
            return HttpResponse('Error processing LTI Outcomes', status=500)

@method_decorator(csrf_exempt, name='dispatch')
class CaliperAnalyticsView(View):
    def post(self, request, *args, **kwargs):
        try:
            # Parse JSON payload
            data = json.loads(request.body)

            # Validate payload structure (simplified for example)
            if 'event' not in data:
                return JsonResponse({'success': False, 'error': 'Invalid Caliper payload'}, status=400)

            # Log or save the event
            CaliperEvent.objects.create(
                user=request.user if request.user.is_authenticated else None,
                event_type=data.get('eventType', 'unknown'),
                event_data=data
            )

            return JsonResponse({'success': True, 'message': 'Caliper event processed successfully'})
        except Exception as e:
            logger.error(f"Error processing Caliper Analytics: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

@require_http_methods(["GET", "POST"])
def enroll_with_code(request):
    if request.method == "POST":
        try:
            email = request.POST.get('email')
            code = request.POST.get('code')
            
            if not email or not code:
                messages.error(request, 'Both email and code are required.')
                return redirect('courses:enroll_with_code')
            
            # Find the enrollment code
            try:
                enrollment_code = EnrollmentCode.objects.get(email=email, code=code)
            except EnrollmentCode.DoesNotExist:
                messages.error(request, 'Invalid enrollment code or email.')
                return redirect('courses:enroll_with_code')
            
            course_instance = enrollment_code.course_instance
            
            # Get or create user
            user = User.objects.filter(email=email).first()
            if not user:
                # Create new user with email as username
                username = email.split('@')[0]
                base_username = username
                counter = 1
                # Ensure unique username
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=code  # Using enrollment code as initial password
                )
                user.is_student = True
                user.save()
            
            # Check if already enrolled
            if Enrollment.objects.filter(student=user, course_instance=course_instance).exists():
                messages.warning(request, 'You are already enrolled in this course.')
            else:
                # Create enrollment and associated records
                enrollment = Enrollment.objects.create(
                    student=user,
                    course_instance=course_instance
                )
                
                # Create CourseProgress
                total_modules = Module.objects.filter(unit__course=course_instance.course).count()
                CourseProgress.objects.create(
                    enrollment=enrollment,
                    total_modules=total_modules
                )
                
                # Create ModuleProgress records for each module
                module_progress_list = []
                for module in Module.objects.filter(unit__course=course_instance.course):
                    module_progress_list.append(
                        ModuleProgress(
                            user=user,
                            module=module,
                            enrollment=enrollment
                        )
                    )
                ModuleProgress.objects.bulk_create(module_progress_list)
                
                messages.success(request, 'Successfully enrolled in the course!')
            
            # Log the user in
            if not request.user.is_authenticated:
                login(request, user)
            
            return redirect('courses:course_detail', instance_id=course_instance.id)
            
        except Exception as e:
            logger.error(f"Error in enrollment process: {str(e)}")
            messages.error(request, 'An error occurred during enrollment. Please try again.')
            return redirect('courses:enroll_with_code')
    
    return render(request, 'courses/enroll_with_code.html')

@require_POST
@login_required
def create_enrollment_code(request, course_instance_id):
    if not request.user.is_instructor:
        return JsonResponse({'success': False, 'error': 'Permission denied.'})

    try:
        data = json.loads(request.body)
        name = data.get('name')
        email = data.get('email')
        code = data.get('code')

        if not (name and email and code):
            return JsonResponse({'success': False, 'error': 'All fields are required.'})

        course_instance = get_object_or_404(CourseInstance, id=course_instance_id)
        
        # Check if user already exists
        existing_user = User.objects.filter(email=email).first()
        
        # Check if user is already enrolled
        if existing_user:
            existing_enrollment = Enrollment.objects.filter(
                student=existing_user, 
                course_instance=course_instance
            ).exists()
            if existing_enrollment:
                return JsonResponse({
                    'success': False, 
                    'error': 'User is already enrolled in this course.',
                    'status': 'already_enrolled'
                })

        # Create or get enrollment code
        enrollment_code, created = EnrollmentCode.objects.get_or_create(
            email=email,
            course_instance=course_instance,
            defaults={'code': code}
        )

        if not created:
            return JsonResponse({
                'success': False,
                'error': 'An enrollment code already exists for this email.',
                'status': 'code_exists',
                'existing_code': enrollment_code.code
            })

        # Create or update user
        if existing_user:
            user = existing_user
            status = 'existing_user'
        else:
            user = User.objects.create_user(
                username=email,
                email=email,
                password=code
            )
            user.first_name = name.split()[0] if ' ' in name else name
            user.last_name = name.split()[-1] if ' ' in name else ''
            user.is_student = True
            user.save()
            status = 'new_user'

        # Create enrollment
        enrollment, created = Enrollment.objects.get_or_create(student=user, course_instance=course_instance)

        return JsonResponse({
            'success': True,
            'status': status,
            'message': 'Enrollment code created successfully.'
        })

    except Exception as e:
        logger.error("Error creating enrollment code: %s", str(e))
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
def update_module_progress(request, module_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    module = get_object_or_404(Module, id=module_id)
    print(module)
    print(module.unit)
    print(module.unit.course)
    course = module.unit.course
    
    # Don't update progress for instructors of this course
    if course.instructors.filter(id=request.user.id).exists():
        return JsonResponse({
            'success': True,
            'message': 'Progress not tracked for instructors'
        })
    
    try:
        data = json.loads(request.body)
        
        # Find the active course instance for this user and module
        course_instance = CourseInstance.objects.filter(
            course=course,
            enrollments__student=request.user,
            active=True
        ).first()
        
        if not course_instance:
            return JsonResponse({'error': 'No active enrollment found'}, status=404)
        
        # Now include course_instance in the get_or_create_progress call
        module_progress, created = ModuleProgress.get_or_create_progress(
            user=request.user,
            module=module,
            course_instance=course_instance
        )
        module_progress.update_from_activity_attempt(data)
        
        # Get updated course progress through the enrollment
        course_progress = CourseProgress.objects.get(
            enrollment__student=request.user,
            enrollment__course_instance=course_instance
        )
        course_progress.update_progress()
        
        return JsonResponse({
            'success': True,
            'module_progress': {
                'progress': module_progress.progress,
                'is_complete': module_progress.is_complete,
                'score': module_progress.score
            },
            'course_progress': {
                'overall_progress': course_progress.overall_progress,
                'overall_score': course_progress.overall_score,
                'modules_completed': course_progress.modules_completed
            }
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
def duplicate_course_instance(request, course_instance_id):
    """
    Duplicates a course instance with a new group name.
    """
    if not request.user.is_instructor:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
        
    try:
        data = json.loads(request.body)
        new_group_name = data.get('group_name')
        
        if not new_group_name:
            return JsonResponse({'success': False, 'error': 'Group name is required'})
            
        course_instance = get_object_or_404(CourseInstance, id=course_instance_id)
        
        # Check if user is instructor for this course
        if not course_instance.instructors.filter(id=request.user.id).exists():
            return JsonResponse({'success': False, 'error': 'Permission denied'})
            
        # Duplicate the course instance
        new_instance = course_instance.duplicate(new_group_name)
        
        return JsonResponse({'success': True, 'new_instance_id': new_instance.id})
        
    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)})
    except Exception as e:
        logger.error(f"Error duplicating course instance: {str(e)}")
        return JsonResponse({'success': False, 'error': 'An error occurred while duplicating the course'})

@require_GET
def check_group_name(request):
    """
    Check if a group name is available for a specific course.
    """
    try:
        group_name = request.GET.get('group_name', '').strip()
        course_id = request.GET.get('course_id')
        
        if not group_name:
            return JsonResponse({'available': False, 'error': 'Group name is required'})
            
        if not course_id:
            return JsonResponse({'available': False, 'error': 'Course ID is required'})
            
        # Check if the group name exists for this specific course
        exists = CourseInstance.objects.filter(
            course_id=course_id,
            group_name=group_name
        ).exists()
        
        return JsonResponse({'available': not exists})
        
    except Exception as e:
        logger.error(f"Error checking group name: {str(e)}", exc_info=True)
        return JsonResponse(
            {'available': False, 'error': str(e)}, 
            status=400
        )

@login_required
@require_POST
def create_course_instance(request, course_id):
    """
    Creates a new instance of an existing course.
    """
    logger.info(f"Attempting to create course instance for course_id: {course_id}, user: {request.user}")
    
    if not request.user.is_instructor:
        logger.warning(f"Permission denied: User {request.user} is not an instructor")
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    try:
        # Log request body
        logger.debug(f"Request body: {request.body}")
        data = json.loads(request.body)
        group_name = data.get('group_name', '').strip()
        
        logger.info(f"Parsed group_name: {group_name}")
        
        if not group_name:
            logger.warning("Group name is required but was empty")
            return JsonResponse({'success': False, 'error': 'Group name is required'})
        
        # Log course lookup attempt
        logger.info(f"Looking up course with id: {course_id}")
        course = get_object_or_404(Course, id=course_id)
        logger.info(f"Found course: {course.title}")
        
        # Check instructor permission
        if not course.instructors.filter(id=request.user.id).exists():
            logger.warning(f"Permission denied: User {request.user} is not an instructor for course {course_id}")
            return JsonResponse({'success': False, 'error': 'Permission denied'})
        
        # Check if instance with this group name already exists
        if CourseInstance.objects.filter(course=course, group_name=group_name).exists():
            logger.warning(f"Group name '{group_name}' already exists for course {course_id}")
            return JsonResponse({'success': False, 'error': 'A session with this group name already exists'})
        
        # Create new course instance
        logger.info(f"Creating new course instance with group_name: {group_name}")
        instance = CourseInstance.objects.create(
            course=course,
            group_name=group_name
        )
        instance.instructors.add(request.user)
        logger.info(f"Successfully created course instance id: {instance.id}")
        
        return JsonResponse({'success': True, 'instance_id': instance.id})
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Invalid JSON in request'})
    except Course.DoesNotExist:
        logger.error(f"Course not found: {course_id}")
        return JsonResponse({'success': False, 'error': 'Course not found'})
    except Exception as e:
        logger.error(f"Unexpected error creating course instance: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'An unexpected error occurred'})

@login_required
def course_details(request, course_id):
    """
    Returns JSON details about a course and its instances for deletion confirmation
    """
    try:
        course = Course.objects.get(id=course_id)
        
        # Check if user is authorized to delete this course
        if request.user not in course.instructors.all():
            return JsonResponse({
                'error': 'Not authorized to delete this course'
            }, status=403)
        
        # Get all instances of this course
        instances = CourseInstance.objects.filter(course=course).annotate(
            enrollment_count=Count('enrollments')
        )
        
        # Prepare the response data
        data = {
            'course': {
                'id': course.id,
                'title': course.title,
                'description': course.description
            },
            'instances': [{
                'id': instance.id,
                'group_name': instance.group_name,
                'enrollment_count': instance.enrollment_count
            } for instance in instances]
        }
        
        return JsonResponse(data)
        
    except Course.DoesNotExist:
        return JsonResponse({
            'error': 'Course not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error fetching course details: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': str(e)
        }, status=500)

@login_required
@require_POST
def delete_course(request, course_id):
    """
    Deletes a course and all its instances.
    """
    if not request.user.is_instructor:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
        
    try:
        course = Course.objects.get(id=course_id, instructors=request.user)
        
        # Get the count of instances and enrollments for logging
        instances = CourseInstance.objects.filter(course=course)
        instance_count = instances.count()
        enrollment_count = Enrollment.objects.filter(course_instance__in=instances).count()
        
        # Delete the course (this will cascade delete instances and enrollments)
        course.delete()
        
        logger.info(f"Deleted course {course_id} with {instance_count} instances and {enrollment_count} enrollments")
        return JsonResponse({'success': True})
        
    except Course.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Course not found'})
    except Exception as e:
        logger.error(f"Error deleting course: {str(e)}")
        return JsonResponse({'success': False, 'error': 'An error occurred while deleting the course'})

@login_required
def get_course_enrollments(request, course_instance_id):
    try:
        course_instance = CourseInstance.objects.get(id=course_instance_id)
        
        # Check if user is authorized
        if request.user not in course_instance.instructors.all():
            return JsonResponse({'error': 'Not authorized'}, status=403)
        
        # Get total modules count for the course
        total_modules = Module.objects.filter(unit__course=course_instance.course).count()
        
        enrollments_data = []
        for enrollment in course_instance.enrollments.select_related('student', 'course_progress').all():
            enrollments_data.append({
                'id': enrollment.id,
                'student': {
                    'email': enrollment.student.email,
                    'username': enrollment.student.username
                },
                'progress': {
                    'modules_completed': enrollment.course_progress.modules_completed if hasattr(enrollment, 'course_progress') else 0,
                    'total_modules': total_modules,  # Use the calculated total
                    'overall_score': enrollment.course_progress.overall_score if hasattr(enrollment, 'course_progress') else 0.0
                }
            })
        
        return JsonResponse({
            'success': True,
            'enrollments': enrollments_data
        })
        
    except CourseInstance.DoesNotExist:
        return JsonResponse({'error': 'Course instance not found'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching enrollments: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
def bulk_enroll_students(request, course_instance_id):
    print("\n=== Starting bulk enrollment process ===")
    try:
        course_instance = CourseInstance.objects.get(id=course_instance_id)
        print(f"Found course instance: {course_instance.id} - {course_instance.course.title}")
        
        if request.user not in course_instance.instructors.all():
            print(f"User {request.user.username} not authorized")
            return JsonResponse({'error': 'Not authorized'}, status=403)
        
        data = json.loads(request.body)
        emails = data.get('emails', [])
        print(f"Processing emails: {emails}")
        
        success_count = 0
        error_count = 0
        new_enrollments = []
        error_details = []
        
        for email in emails:
            print(f"\nProcessing email: {email}")
            try:
                validate_email(email)
                print("Email validation passed")
                
                # Get or create user with email as username
                user, user_created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        'username': email,  # Use full email as username
                        'is_student': True
                    }
                )
                print(f"User {'created' if user_created else 'found'}: {user.username}")
                
                # Check enrollment
                print(f"Checking enrollment for user {user.username} in course instance {course_instance.id}")
                enrollment, enrollment_created = Enrollment.objects.get_or_create(
                    student=user,
                    course_instance=course_instance,
                    defaults={'active': True}
                )
                print(f"Enrollment {'created' if enrollment_created else 'already exists'}")
                
                if enrollment_created:
                    new_enrollments.append({
                        'id': enrollment.id,
                        'student': {
                            'email': user.email
                        },
                        'progress': {
                            'modules_completed': 0,
                            'total_modules': Module.objects.filter(unit__course=course_instance.course).count(),
                            'overall_score': 0.0
                        }
                    })
                    success_count += 1
                    print("Enrollment process completed successfully")
                else:
                    error_count += 1
                    error_details.append(f"{email}: Already enrolled in this course session")
                    print("Skipped - already enrolled")
                    
            except ValidationError as ve:
                print(f"Validation error for {email}: {str(ve)}")
                error_count += 1
                error_details.append(f"{email}: Invalid email format")
                continue
            except Exception as e:
                print(f"Unexpected error for {email}: {str(e)}")
                error_count += 1
                error_details.append(f"{email}: {str(e)}")
                logger.error(f"Error enrolling {email}: {str(e)}", exc_info=True)
                continue
        
        print("\n=== Bulk enrollment process completed ===")
        print(f"Successes: {success_count}, Errors: {error_count}")
        print(f"Error details: {error_details}")
        
        return JsonResponse({
            'success': True,
            'success_count': success_count,
            'error_count': error_count,
            'error_details': error_details,
            'enrollments': new_enrollments
        })
        
    except CourseInstance.DoesNotExist:
        print(f"Course instance {course_instance_id} not found")
        return JsonResponse({'error': 'Course instance not found'}, status=404)
    except Exception as e:
        print(f"Critical error in bulk enrollment: {str(e)}")
        logger.error(f"Error in bulk enrollment: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
def remove_enrollment(request, enrollment_id):
    """
    Remove a student's enrollment from a course instance
    """
    try:
        enrollment = Enrollment.objects.select_related('course_instance').get(id=enrollment_id)
        
        # Check if user is authorized (must be an instructor of the course)
        if request.user not in enrollment.course_instance.instructors.all():
            return JsonResponse({'error': 'Not authorized'}, status=403)
        
        # Store info for logging
        student_email = enrollment.student.email
        course_name = enrollment.course_instance.course.title
        
        # Delete the enrollment (this will cascade to related records)
        enrollment.delete()
        
        # Log the action
        logger.info(f"Removed enrollment of {student_email} from {course_name} by {request.user.username}")
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully removed {student_email} from the course'
        })
        
    except Enrollment.DoesNotExist:
        return JsonResponse({'error': 'Enrollment not found'}, status=404)
    except Exception as e:
        logger.error(f"Error removing enrollment: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
def delete_course_instance(request, instance_id):
    try:
        instance = CourseInstance.objects.get(id=instance_id)
        
        # Check if user is an instructor for this course instance
        if request.user not in instance.instructors.all():
            return JsonResponse({'error': 'Not authorized'}, status=403)
            
        instance.delete()
        return JsonResponse({'success': True})
    except CourseInstance.DoesNotExist:
        return JsonResponse({'error': 'Course instance not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def create_semester_course(request):
    logger.debug("Entered create_semester_course view")
    
    if not request.user.is_instructor:
        logger.warning(f"Permission denied for user: {request.user}")
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    course_id = request.GET.get('course_id')
    logger.debug(f"Received course_id: {course_id}")

    # Render the template that handles the course creation process
    try:
        response = render(request, 'courses/create_semester_course.html', {
            'course_id': course_id
        })
        logger.debug("Successfully rendered create_semester_course.html")
        return response
    except Exception as e:
        logger.error(f"Error rendering template: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'Internal server error'}, status=500)