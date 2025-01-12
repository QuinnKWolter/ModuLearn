from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Course, Module, Enrollment, Unit, StudentScore, CaliperEvent, EnrollmentCode, CourseProgress, ModuleProgress
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
from django.views.decorators.http import require_POST
import os
from django.core.serializers.json import DjangoJSONEncoder
import uuid
from django.views.decorators.http import require_http_methods

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
    courses = []
    
    if request.user.is_authenticated:
        if request.user.is_student:
            # Get only enrolled courses for students
            enrollments = Enrollment.objects.filter(
                student=request.user
            ).select_related('course', 'course_progress')
            
            # Convert to list of courses with attached enrollment info
            for enrollment in enrollments:
                course = enrollment.course
                course.user_enrollment = enrollment
                courses.append(course)
        elif request.user.is_instructor:
            # Get courses where user is instructor
            taught_courses = Course.objects.filter(instructors=request.user)
            
            # Get enrollments where instructor is enrolled as student
            student_enrollments = Enrollment.objects.filter(
                student=request.user
            ).select_related('course', 'course_progress')
            
            # Add taught courses
            for course in taught_courses:
                courses.append(course)
            
            # Add enrolled courses
            for enrollment in student_enrollments:
                course = enrollment.course
                course.user_enrollment = enrollment
                if course not in courses:  # Avoid duplicates
                    courses.append(course)
    
    return render(request, 'courses/course_list.html', {
        'courses': courses,
        'lti_data': getattr(request.user, 'lti_data', {})
    })

@login_required
def course_detail(request, course_id):
    """
    Displays details of a specific course and handles enrollment.
    """
    course = get_object_or_404(Course, id=course_id)
    enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()
    
    # Get course progress through enrollment if it exists
    course_progress = None
    if enrolled:
        course_progress, created = CourseProgress.get_or_create_progress(request.user, course)
    
    units = course.units.prefetch_related('modules')

    # Pre-compute module progress
    module_progress_data = {}
    if enrolled:
        for unit in units:
            for module in unit.modules.all():
                module_progress_data[module.id] = module.get_student_progress(request.user)
    
    # Check if user is instructor for this course
    is_instructor = request.user.is_instructor and course.instructors.filter(id=request.user.id).exists()
    
    context = {
        'course': course,
        'enrolled': enrolled,
        'course_progress': course_progress,
        'units': units,
        'module_progress_data': module_progress_data,
        'is_instructor': is_instructor,
    }

    # Handle enrollment POST request
    if request.method == 'POST' and not enrolled and request.user.is_student:
        enrollment = Enrollment.objects.create(student=request.user, course=course)
        messages.success(request, f'You have been enrolled in {course.title}')
        return redirect('courses:course_detail', course_id=course_id)

    return render(request, 'courses/course_detail.html', context)

@login_required
def module_detail(request, course_id, unit_id, module_id):
    """
    Displays details of a specific module within a course.
    """
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    module = get_object_or_404(Module, id=module_id, unit=unit)
    enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()

    # Determine if the user is an instructor for this course
    is_instructor = request.user.is_instructor and course.instructors.filter(id=request.user.id).exists()

    if not enrolled and not is_instructor:
        messages.error(request, 'You must be enrolled in the course to access modules.')
        return redirect('courses:course_detail', course_id=course_id)

    module_progress = ModuleProgress.objects.filter(
        enrollment__student=request.user,
        enrollment__course__id=course_id,
        module=module
    ).first()
    
    # Properly serialize the state data
    state_data = json.dumps(module_progress.state_data if module_progress else None, cls=DjangoJSONEncoder)
    
    return render(request, 'courses/module_page.html', {
        'module': module,
        'module_progress': module_progress,
        'state_data': state_data,
        'is_instructor': is_instructor
    })

@login_required
def module_render(request, module_id):
    module = get_object_or_404(Module, id=module_id)
    course = module.unit.course
    
    # Check if user has access to this module
    is_instructor = course.instructors.filter(id=request.user.id).exists()
    is_enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()
    
    if not (is_instructor or is_enrolled):
        return HttpResponseForbidden("You don't have access to this module")
    
    # Get or create progress using the updated method
    module_progress, created = ModuleProgress.get_or_create_progress(request.user, module)
    
    # Get state data for the module
    state_data = module_progress.state_data if module_progress else None
    
    context = {
        'module': module,
        'state_data': state_data,
        'is_instructor': is_instructor,  # Pass this to template
        'module_progress': module_progress
    }
    
    # Choose template based on module type
    template_name = f'courses/{module.module_type}.html'
    return render(request, template_name, context)

@login_required
def unenroll(request, course_id):
    """
    Allows a user to unenroll from a course.
    """
    course = get_object_or_404(Course, id=course_id)
    enrollment = Enrollment.objects.filter(student=request.user, course=course).first()

    if enrollment:
        enrollment.delete()
        messages.success(request, f'You have unenrolled from {course.title}.')
    else:
        messages.error(request, 'You are not enrolled in this course.')

    return redirect('courses:course_detail', course_id=course_id)

@login_required
def create_course(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            if 'course_id' in data:
                # Fetch JSON from external API
                course_data = fetch_course_details(data['course_id'])
            elif 'course_data' in data:
                # Use provided JSON directly
                course_data = data['course_data']
            else:
                return JsonResponse({'success': False, 'error': 'Invalid input'})
            
            # Create course from the JSON data
            create_course_from_json(course_data, request.user)
            return JsonResponse({'success': True})
            
        except Exception as e:
            logger.error("Error creating course: %s", str(e))
            logger.error(traceback.format_exc())
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def launch_iframe_module(request, module_id):
    module = get_object_or_404(Module, id=module_id)
    course = module.unit.course
    
    # Check if user has access to this module
    is_instructor = course.instructors.filter(id=request.user.id).exists()
    is_enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()
    
    if not (is_instructor or is_enrolled):
        return HttpResponseForbidden("You don't have access to this module")
    
    # Get or create progress using the updated method
    module_progress, created = ModuleProgress.get_or_create_progress(request.user, module)
    
    # Get state data for the module
    state_data = module_progress.state_data if module_progress else None
    
    # Parse the original URL and add LTI parameters
    parsed_url = urlparse(module.iframe_url)
    query_params = parse_qs(parsed_url.query)
    
    # Add your existing LTI parameters here...
    
    # Reconstruct the URL
    new_query_string = urlencode(query_params, doseq=True)
    new_url = urlunparse(parsed_url._replace(query=new_query_string))
    
    context = {
        'module': module,
        'iframe_url': new_url,
        'state_data': json.dumps(state_data) if state_data else None,
        'is_instructor': is_instructor
    }
    
    return render(request, 'courses/module_frame.html', context)

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
            
            course = enrollment_code.course
            
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
            if Enrollment.objects.filter(student=user, course=course).exists():
                messages.warning(request, 'You are already enrolled in this course.')
            else:
                # Create enrollment and associated records
                enrollment = Enrollment.objects.create(student=user, course=course)
                
                # Create CourseProgress
                total_modules = Module.objects.filter(unit__course=course).count()
                CourseProgress.objects.create(
                    enrollment=enrollment,
                    total_modules=total_modules
                )
                
                # Create ModuleProgress records for each module
                module_progress_list = []
                for module in Module.objects.filter(unit__course=course):
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
            
            return redirect('courses:course_detail', course_id=course.id)
            
        except Exception as e:
            logger.error(f"Error in enrollment process: {str(e)}")
            messages.error(request, 'An error occurred during enrollment. Please try again.')
            return redirect('courses:enroll_with_code')
    
    return render(request, 'courses/enroll_with_code.html')

@require_POST
@login_required
def create_enrollment_code(request, course_id):
    logger.info("Received request to create enrollment code")
    if not request.user.is_instructor:
        logger.warning("Permission denied for user: %s", request.user)
        return JsonResponse({'success': False, 'error': 'Permission denied.'})

    try:
        data = json.loads(request.body)
        logger.debug("Request data: %s", data)
        name = data.get('name')
        email = data.get('email')
        code = data.get('code')

        if not (name and email and code):
            logger.error("Missing fields in request data")
            return JsonResponse({'success': False, 'error': 'All fields are required.'})

        course = get_object_or_404(Course, id=course_id)
        
        # Check if user already exists
        existing_user = User.objects.filter(email=email).first()
        
        # Check if user is already enrolled
        if existing_user:
            existing_enrollment = Enrollment.objects.filter(student=existing_user, course=course).exists()
            if existing_enrollment:
                return JsonResponse({
                    'success': False, 
                    'error': 'User is already enrolled in this course.',
                    'status': 'already_enrolled'
                })

        # Create or get enrollment code
        enrollment_code, created = EnrollmentCode.objects.get_or_create(
            email=email,
            course=course,
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
        enrollment, created = Enrollment.objects.get_or_create(student=user, course=course)

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
        module_progress, created = ModuleProgress.get_or_create_progress(request.user, module)
        module_progress.update_from_activity_attempt(data)
        
        # Get updated course progress
        course_progress = CourseProgress.objects.get(enrollment__student=request.user, enrollment__course=course)
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