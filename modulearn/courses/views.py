from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Course, Module, Enrollment, Unit, StudentScore, CaliperEvent, EnrollmentCode
from django.contrib.auth import get_user_model
from django.http import JsonResponse, HttpResponse
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

User = get_user_model()

# Configure logging
logger = logging.getLogger(__name__)

def course_list(request):
    """
    Displays a list of courses the user is enrolled in.
    """
    if request.user.is_authenticated and request.user.is_student:
        enrollments = Enrollment.objects.filter(student=request.user)
        courses = [enrollment.course for enrollment in enrollments]
    else:
        courses = []

    # Get LTI context data if available
    lti_data = {}
    if hasattr(request.user, 'lti_data') and request.user.lti_data:
        lti_data = {
            'name': request.user.lti_data.get('name'),
            'email': request.user.lti_data.get('email'),
            'roles': request.user.lti_data.get('https://purl.imsglobal.org/spec/lti/claim/roles', []),
            'context': request.user.lti_data.get('https://purl.imsglobal.org/spec/lti/claim/context', {}),
            'platform': request.user.lti_data.get('https://purl.imsglobal.org/spec/lti/claim/tool_platform', {}),
            'resource_link': request.user.lti_data.get('https://purl.imsglobal.org/spec/lti/claim/resource_link', {}),
            'picture': request.user.lti_data.get('picture'),
        }
    
    return render(request, 'courses/course_list.html', {
        'courses': courses,
        'lti_data': lti_data
    })

@login_required
def course_detail(request, course_id):
    """
    Displays details of a specific course and handles enrollment.
    """
    course = get_object_or_404(Course, id=course_id)
    units = course.units.all()
    enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()

    # Determine if the user is an instructor for this course
    is_instructor = request.user.is_instructor and course.instructors.filter(id=request.user.id).exists()

    if request.method == 'POST' and not enrolled and request.user.is_student:
        Enrollment.objects.create(student=request.user, course=course)
        messages.success(request, f'You have enrolled in {course.title}.')
        return redirect('courses:course_detail', course_id=course_id)

    return render(request, 'courses/course_detail.html', {
        'course': course,
        'units': units,
        'enrolled': enrolled,
        'is_instructor': is_instructor,
        'year': datetime.now().year
    })

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

    # Redirect to module render view if it's an external iframe
    if module.module_type == 'external_iframe':
        return redirect('courses:module_render', module_id=module.id)

    return render(request, 'courses/module_detail.html', {'module': module})

@login_required
def module_render(request, module_id):
    """
    Renders the smart content for a specific module.
    """
    module = get_object_or_404(Module, id=module_id)
    course = module.unit.course

    # Check if the user is enrolled or is an instructor
    enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()
    is_instructor = request.user.is_instructor and course.instructors.filter(id=request.user.id).exists()

    if not enrolled and not is_instructor:
        messages.error(request, 'You must be enrolled in the course to access this module.')
        return redirect('courses:course_detail', course_id=course.id)

    # Handle module types
    if module.module_type == 'external_iframe':
        # Generate LTI launch URL
        lti_launch_url = request.build_absolute_uri(reverse('lti:launch'))
        template_name = 'courses/external_iframe.html'
        context = {
            'module': module,
            'lti_launch_url': lti_launch_url,
            'year': datetime.now().year
        }
    else:
        # Existing logic for other module types
        template_name = 'courses/module_render.html'
        context = {'module': module}

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
            if 'course_data' in data:
                # Handle raw JSON input
                create_course_from_json(data['course_data'], request.user)
                return JsonResponse({'success': True})
            elif 'course_id' in data:
                # Handle Course ID input
                fetch_course_details(data['course_id'])
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False, 'error': 'Invalid input'})
        
        except Exception as e:
            # Log the exception with a stack trace
            logger.error("Error creating course: %s", str(e))
            logger.error(traceback.format_exc())
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def launch_iframe_module(request, module_id):
    module = get_object_or_404(Module, id=module_id)
    
    # Ensure the module is of type 'external_iframe'
    if module.module_type != 'external_iframe':
        return HttpResponse('Invalid module type for LTI launch.', status=400)

    # Use the LTI_CONSUMER_CONFIG for launching the tool
    lti_consumer_config = settings.LTI_CONSUMER_CONFIG

    # Generate LTI launch parameters
    lti_params = {
        "iss": request.build_absolute_uri('/'),  # Your platform's URL
        "aud": lti_consumer_config['client_id'],
        "sub": request.user.username,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "nonce": "unique-nonce-value",
        "state": "unique-state-value",
        "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiResourceLinkRequest",
        "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
        "https://purl.imsglobal.org/spec/lti/claim/resource_link": {
            "id": str(module.id)
        },
        # Add other necessary claims
    }

    # Sign the JWT
    try:
        # Use an absolute path
        private_key_path = os.path.join(settings.BASE_DIR, 'modulearn', 'private.key')

        # Open the private key file
        with open(private_key_path, 'rb') as key_file:
            private_key = key_file.read()
        lti_jwt = jwt.encode(lti_params, private_key, algorithm='RS256')
    except Exception as e:
        logger.error(f"Error signing JWT: {e}")
        return HttpResponse('Error generating LTI launch token.', status=500)

    # Parse the existing iframe_url to preserve its query parameters
    parsed_url = urlparse(module.iframe_url)
    query_params = parse_qs(parsed_url.query)

    # Add LTI parameters to the existing query parameters
    query_params['id_token'] = lti_jwt
    query_params['state'] = 'unique-state-value'

    # Reconstruct the URL with all parameters
    new_query_string = urlencode(query_params, doseq=True)
    new_url = urlunparse(parsed_url._replace(query=new_query_string))

    return redirect(new_url)

@csrf_exempt
def log_lti_response(request):
    """
    Logs the response received from the LTI tool iframe.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            logger.info("LTI Response Data: %s", data)

            # Optional: Save data to the database
            # Example:
            # LTIResult.objects.create(
            #     user=request.user,
            #     module_id=module_id,
            #     result=data['result']
            # )

            return JsonResponse({'success': True, 'message': 'LTI response logged successfully'})
        except Exception as e:
            logger.error(f"Error logging LTI response: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=400)

@method_decorator(csrf_exempt, name='dispatch')
class LTIOutcomesView(View):
    def post(self, request, *args, **kwargs):
        try:
            # Parse XML payload
            tree = ET.ElementTree(ET.fromstring(request.body))
            root = tree.getroot()

            # Extract necessary data
            lis_result_sourcedid = root.find('.//lis_result_sourcedid').text
            score = float(root.find('.//score').text)

            # Log or save the score
            StudentScore.objects.create(
                user=request.user,
                lis_result_sourcedid=lis_result_sourcedid,
                score=score
            )

            # Return success response
            response_xml = """<?xml version="1.0" encoding="UTF-8"?>
            <imsx_POXEnvelopeResponse xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
                <imsx_POXHeader>
                    <imsx_POXResponseHeaderInfo>
                        <imsx_version>V1.0</imsx_version>
                        <imsx_messageIdentifier>123456789</imsx_messageIdentifier>
                        <imsx_statusInfo>
                            <imsx_codeMajor>success</imsx_codeMajor>
                            <imsx_severity>status</imsx_severity>
                            <imsx_description>Score processed successfully</imsx_description>
                        </imsx_statusInfo>
                    </imsx_POXResponseHeaderInfo>
                </imsx_POXHeader>
                <imsx_POXBody>
                    <replaceResultResponse/>
                </imsx_POXBody>
            </imsx_POXEnvelopeResponse>"""
            return HttpResponse(response_xml, content_type='application/xml')
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

def enroll_with_code(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        code = request.POST.get('code')
        enrollment_code = EnrollmentCode.objects.filter(code=code, email=email).first()

        if enrollment_code:
            user, created = User.objects.get_or_create(email=email, defaults={'username': email, 'password': enrollment_code.code})
            if created:
                user.set_password(enrollment_code.code)
                user.save()
            login(request, user)
            course = enrollment_code.course
            Enrollment.objects.get_or_create(student=user, course=course)
            messages.success(request, f'You have been enrolled in {course.title}.')
            return redirect('courses:course_detail', course_id=course.id)
        else:
            messages.error(request, 'Invalid enrollment code or email.')
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
        EnrollmentCode.objects.create(code=code, email=email, course=course)

        user, created = User.objects.get_or_create(email=email, defaults={'username': email, 'password': code})
        if created:
            user.set_password(code)
            user.save()

        # Create an enrollment for the user in the course
        Enrollment.objects.get_or_create(student=user, course=course)

        logger.info("Enrollment code created successfully for email: %s", email)
        return JsonResponse({'success': True})
    except Exception as e:
        logger.error("Error creating enrollment code: %s", str(e))
        return JsonResponse({'success': False, 'error': str(e)})