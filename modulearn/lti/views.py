from django.shortcuts import redirect
from django.conf import settings
from django.contrib.auth import login
from accounts.models import User
from django.http import JsonResponse, HttpResponse
from jwcrypto import jwk
import jwt
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from pylti1p3.contrib.django import (
    DjangoMessageLaunch,
    DjangoOIDCLogin,
    DjangoCacheDataStorage,
)
from pylti1p3.tool_config import ToolConfDict
import json
from courses.models import Course, Module, CourseInstance, Enrollment, CourseProgress
import logging
from modulearn.settings import get_primary_domain

logger = logging.getLogger(__name__)

# ----------------------
# LTI 1.3 Views
# ----------------------

def lti13_jwks(request):
    """JWKS endpoint for LTI 1.3"""
    platform_config = settings.LTI_CONFIG['https://saltire.lti.app/platform']
    with open(platform_config['public_key_file'], 'rb') as f:
        public_key_pem = f.read()
    key = jwk.JWK.from_pem(public_key_pem)
    public_key_json = key.export_public()
    public_key_dict = json.loads(public_key_json)
    return JsonResponse({'keys': [public_key_dict]})

@csrf_exempt
def lti13_login(request):
    """OIDC login endpoint for LTI 1.3"""
    logger.info("LTI 1.3 login request received")
    logger.info(f"Request method: {request.method}")
    logger.info(f"GET parameters: {request.GET}")
    logger.info(f"POST parameters: {request.POST}")

    # Add state parameter validation and storage
    state = request.GET.get('state')
    nonce = request.GET.get('nonce')

    if not state:
        return HttpResponse("Missing 'state' parameter in OIDC login request.", status=400)
    
    # Store state and nonce in session
    request.session['oidc_state'] = state
    request.session['oidc_nonce'] = nonce
    request.session.save()

    tool_conf = ToolConfDict(settings.LTI_CONFIG)
    launch_data_storage = DjangoCacheDataStorage()

    oidc_login = DjangoOIDCLogin(
        request,
        tool_conf,
        launch_data_storage=launch_data_storage
    )
    
    launch_url = request.build_absolute_uri(reverse('lti:launch')).replace("http://", "https://")
    logger.info(f"Login Redirect URI: {launch_url}")

    response = oidc_login.redirect(launch_url)
    return response

def handle_lti13_launch(request):
    """Handle LTI 1.3 launch requests"""
    logger.info("Processing LTI 1.3 launch")
    
    # Validate state parameter
    state = request.POST.get('state')
    if not state:
        return HttpResponse("Missing 'state' parameter in LTI launch request.", status=400)

    stored_state = request.session.get('oidc_state')
    if state != stored_state:
        return HttpResponse("Invalid 'state' parameter.", status=400)

    tool_conf = ToolConfDict(settings.LTI_CONFIG)
    launch_data_storage = DjangoCacheDataStorage()

    message_launch = DjangoMessageLaunch(
        request,
        tool_conf,
        launch_data_storage=launch_data_storage
    )

    try:
        message_launch = message_launch.validate()
    except Exception as e:
        logger.error(f"LTI 1.3 validation error: {e}")
        return HttpResponse(f"Launch validation error: {e}", status=400)

    launch_data = message_launch.get_launch_data()
    return process_launch_data(request, launch_data)

# ----------------------
# LTI 1.1 Views
# ----------------------

def handle_lti11_launch(request):
    """Handle LTI 1.1 launch requests"""
    logger.info("Processing LTI 1.1 launch")
    
    # Extract launch parameters
    launch_data = {
        'user_id': request.POST.get('user_id'),
        'roles': request.POST.get('roles', '').split(','),
        'context_id': request.POST.get('context_id'),
        'context_title': request.POST.get('context_title', 'Untitled Course'),
        'resource_link_id': request.POST.get('resource_link_id'),
        'resource_link_title': request.POST.get('resource_link_title'),
        'lis_person_contact_email_primary': request.POST.get('lis_person_contact_email_primary'),
        'lis_person_name_given': request.POST.get('lis_person_name_given'),
        'lis_person_name_family': request.POST.get('lis_person_name_family'),
        # Add Canvas-specific fields
        'custom_canvas_course_id': request.POST.get('custom_canvas_course_id'),
        'custom_canvas_assignment_id': request.POST.get('custom_canvas_assignment_id'),
        'lis_outcome_service_url': request.POST.get('lis_outcome_service_url'),
        'lis_result_sourcedid': request.POST.get('lis_result_sourcedid'),
    }
    
    return process_launch_data(request, launch_data)

# ----------------------
# Shared Launch Processing
# ----------------------

def process_launch_data(request, launch_data):
    """Process launch data common to both LTI 1.1 and 1.3"""
    # Extract user identifiers with fallbacks
    user_id = (
        launch_data.get('sub') or  # LTI 1.3 user ID
        launch_data.get('user_id') or  # LTI 1.1 user ID
        launch_data.get('custom_canvas_user_id')  # Canvas-specific user ID
    )

    if not user_id:
        logger.error("No user identifier found in launch data")
        return HttpResponse('Missing user identifier in launch data.', status=400)

    email = (
        launch_data.get('email') or  # LTI 1.3 email
        launch_data.get('lis_person_contact_email_primary') or  # LTI 1.1 email
        f"{user_id}@canvas.instructure.com"  # Fallback email
    )

    # Get or create user with email as username for better identification
    user, created = User.objects.get_or_create(
        username=email,  # Use email as username for better identification
        defaults={
            'email': email,
            'first_name': launch_data.get('given_name') or launch_data.get('lis_person_name_given', ''),
            'last_name': launch_data.get('family_name') or launch_data.get('lis_person_name_family', ''),
            'canvas_user_id': user_id
        }
    )

    # Update user roles
    roles = launch_data.get('roles', [])
    if isinstance(roles, str):
        roles = roles.split(',')

    user.is_instructor = any(role for role in roles if 'Instructor' in role or 'TeachingAssistant' in role)
    user.is_student = any(role for role in roles if 'Learner' in role or 'Student' in role) or not user.is_instructor
    user.save(update_fields=['is_instructor', 'is_student'])

    # Log the user in before trying to access enrollments
    login(request, user)

    # Store LTI session data
    request.session['lti_launch_data'] = launch_data
    request.session['canvas_user_id'] = user_id
    request.session['is_lti_launch'] = True
    
    # Get the course instance ID
    instance_id = (
        launch_data.get('custom_course_id') or
        request.GET.get('course_id')
    )
    
    if instance_id:
        try:
            course_instance = CourseInstance.objects.get(
                id=instance_id,
                active=True
            )
            
            # Update Canvas context info FIRST
            canvas_course_id = launch_data.get('custom_canvas_course_id')
            canvas_assignment_id = launch_data.get('custom_canvas_assignment_id')
            print(f"Canvas Course ID: {canvas_course_id}")
            print(f"Canvas Assignment ID: {canvas_assignment_id}")
            
            if canvas_course_id and canvas_assignment_id:
                course_instance.canvas_course_id = canvas_course_id
                course_instance.canvas_assignment_id = canvas_assignment_id
                course_instance.lis_outcome_service_url = launch_data.get('lis_outcome_service_url')
                print(f"lis_outcome_service_url: {course_instance.lis_outcome_service_url}")
                course_instance.save()
            
            # Then handle instructor/student specific logic
            if user.is_instructor:
                course_instance.instructors.add(user)
            elif user.is_student:
                enrollment, created = Enrollment.objects.get_or_create(
                    student=user,
                    course_instance=course_instance,
                    defaults={'active': True}
                )
                
                if created or enrollment:
                    course_progress = CourseProgress.objects.get(enrollment=enrollment)
                    course_progress.lis_result_sourcedid = launch_data.get('lis_result_sourcedid')
                    course_progress.save()
            
            return redirect('courses:course_detail', instance_id=course_instance.id)
        except CourseInstance.DoesNotExist:
            logger.error(f"Course instance {instance_id} not found")
    
    # If no instance_id or course not found, continue with normal launch flow
    # Log the user in
    login(request, user)
    logger.info(f"Successfully logged in user: {user.email} (Canvas ID: {user_id})")

    # Redirect to home page
    return redirect('main:home')

# ----------------------
# Main Launch Endpoint
# ----------------------

@csrf_exempt
def lti_launch(request):
    """Main LTI launch endpoint supporting both 1.1 and 1.3"""
    logger.info("LTI launch request received")
    logger.info(f"POST data: {request.POST}")

    if 'id_token' in request.POST:
        return handle_lti13_launch(request)
    elif 'oauth_consumer_key' in request.POST:
        return handle_lti11_launch(request)
    else:
        return HttpResponse("Invalid LTI launch request.", status=400)

# ----------------------
# Configuration Views
# ----------------------

def lti_config(request):
    """XML configuration endpoint"""
    logger.info(f"LTI Config request received from: {request.META.get('HTTP_REFERER', 'Unknown')}")
    
    domain = get_primary_domain()
    launch_url = f"{domain}/modulearn/lti/launch/"
    
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
    <cartridge_basiclti_link 
        xmlns="http://www.imsglobal.org/xsd/imslticc_v1p0"
        xmlns:blti="http://www.imsglobal.org/xsd/imsbasiclti_v1p0"
        xmlns:lticm="http://www.imsglobal.org/xsd/imslticm_v1p0"
        xmlns:lticp="http://www.imsglobal.org/xsd/imslticp_v1p0"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.imsglobal.org/xsd/imslticc_v1p0 http://www.imsglobal.org/xsd/imslticc_v1p0.xsd">
        <blti:title>{settings.LTI_TOOL_CONFIG['title']}</blti:title>
        <blti:description>{settings.LTI_TOOL_CONFIG['description']}</blti:description>
        <blti:launch_url>{launch_url}</blti:launch_url>
        <blti:secure_launch_url>{launch_url}</blti:secure_launch_url>
        <blti:icon>{domain}/static/img/logo_128.png</blti:icon>
        <blti:custom>
            <lticm:property name="canvas_course_id">$Canvas.course.id</lticm:property>
            <lticm:property name="canvas_user_id">$Canvas.user.id</lticm:property>
        </blti:custom>
        <blti:extensions platform="canvas.instructure.com">
            <lticm:property name="privacy_level">public</lticm:property>
            <lticm:property name="selection_height">800</lticm:property>
            <lticm:property name="selection_width">1200</lticm:property>
        </blti:extensions>
    </cartridge_basiclti_link>
    """
    
    logger.info(f"Returning XML config: {xml_content}")
    return HttpResponse(xml_content, content_type='application/xml')
