from django.shortcuts import redirect
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from accounts.models import User
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from urllib.parse import parse_qs, urlparse
from html import escape
from pylti1p3.contrib.django import (
    DjangoMessageLaunch,
    DjangoOIDCLogin,
)
import json
from courses.models import CourseInstance, Enrollment, CourseProgress
import logging
from modulearn.integrations.config import prefixed_path
from modulearn.settings import get_primary_domain
from accounts.email_utils import (
    find_user_by_email,
    normalize_email_address,
    unique_username_for_email,
    unique_username_from_base,
)
from .cache_data_storage import CacheDataStorage
from .models import LTIPlatformRegistration, LTIUserIdentity
from .platforms import build_lti13_tool_conf, lti_setup_payload, normalize_platform_issuer
from modulearn.learning.services.limits import CapacityLimitError, ensure_session_student_capacity

logger = logging.getLogger(__name__)

LTI_CUSTOM_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/custom"
LTI_DEPLOYMENT_ID_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/deployment_id"
LTI_CONTEXT_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/context"
LTI_RESOURCE_LINK_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/resource_link"
LTI_ROLES_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/roles"
LTI_TARGET_LINK_URI_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/target_link_uri"


def apply_lti_roles(user, roles):
    normalized_roles = [str(role).lower() for role in roles]
    launch_is_instructor = any(
        'instructor' in role or 'teachingassistant' in role
        for role in normalized_roles
    )
    launch_is_student = any(
        'learner' in role or 'student' in role
        for role in normalized_roles
    )

    if launch_is_instructor:
        user.is_instructor = True
        user.is_student = False
    elif not user.is_instructor:
        user.is_student = launch_is_student or not normalized_roles

    user.save(update_fields=['is_instructor', 'is_student'])


# ----------------------
# LTI 1.3 Views
# ----------------------

def lti13_jwks(request):
    """JWKS endpoint for LTI 1.3"""
    tool_conf = build_lti13_tool_conf()
    return JsonResponse(tool_conf.get_jwks())

@csrf_exempt
def lti13_login(request):
    """OIDC login endpoint for LTI 1.3"""
    logger.info("LTI 1.3 login request received")
    logger.info(f"Request method: {request.method}")
    logger.info(f"GET parameters: {request.GET}")
    logger.info(f"POST parameters: {request.POST}")

    request_data = request.POST if request.method == 'POST' else request.GET
    incoming_issuer = normalize_platform_issuer(request_data.get('iss', ''))
    tool_conf = build_lti13_tool_conf()
    launch_data_storage = CacheDataStorage()

    oidc_login = DjangoOIDCLogin(
        request,
        tool_conf,
        launch_data_storage=launch_data_storage
    )
    
    launch_url = request.build_absolute_uri(reverse('lti:launch'))
    logger.info(f"Login Redirect URI: {launch_url}")

    try:
        return oidc_login.redirect(launch_url)
    except Exception as e:
        logger.exception("LTI 1.3 login error: %s", e)
        if incoming_issuer and 'not found in settings' in str(e):
            return HttpResponse(
                "LTI 1.3 login error: platform issuer "
                f"{incoming_issuer} is not registered in ModuLearn. "
                "Open the course session's LTI Setup modal as an instructor, "
                "save Moodle's Platform ID / issuer, Client ID, Deployment ID, "
                "Authentication request URL, Access token URL, and Public keyset URL, "
                "then retry the launch.",
                status=400,
            )
        return HttpResponse(f"LTI 1.3 login error: {e}", status=400)

def handle_lti13_launch(request):
    """Handle LTI 1.3 launch requests"""
    logger.info("Processing LTI 1.3 launch")
    
    tool_conf = build_lti13_tool_conf()
    launch_data_storage = CacheDataStorage()

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
        'lti_version_major': '1.1',
        'oauth_consumer_key': request.POST.get('oauth_consumer_key'),
        'user_id': request.POST.get('user_id'),
        'roles': request.POST.get('roles', '').split(','),
        'context_id': request.POST.get('context_id'),
        'context_title': request.POST.get('context_title', 'Untitled Course'),
        'resource_link_id': request.POST.get('resource_link_id'),
        'resource_link_title': request.POST.get('resource_link_title'),
        'lis_person_contact_email_primary': request.POST.get('lis_person_contact_email_primary'),
        'lis_person_name_given': request.POST.get('lis_person_name_given'),
        'lis_person_name_family': request.POST.get('lis_person_name_family'),
        'custom_course_id': request.POST.get('custom_course_id') or request.POST.get('custom_modulearn_course_id'),
        # Add Canvas-specific fields
        'custom_canvas_course_id': request.POST.get('custom_canvas_course_id'),
        'custom_canvas_assignment_id': request.POST.get('custom_canvas_assignment_id'),
        'custom_canvas_user_id': request.POST.get('custom_canvas_user_id'),
        'lis_outcome_service_url': request.POST.get('lis_outcome_service_url'),
        'lis_result_sourcedid': request.POST.get('lis_result_sourcedid'),
    }
    
    return process_launch_data(request, launch_data)

# ----------------------
# Shared Launch Processing
# ----------------------

def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [item.strip() for item in str(value).split(',') if item.strip()]


def _first_audience(value):
    if isinstance(value, list):
        return str(value[0]) if value else ''
    return str(value or '')


def _claim_dict(launch_data, claim):
    value = launch_data.get(claim) or {}
    return value if isinstance(value, dict) else {}


def _get_roles(launch_data):
    return _as_list(launch_data.get(LTI_ROLES_CLAIM) or launch_data.get('roles'))


def _get_deployment_id(launch_data):
    return str(launch_data.get(LTI_DEPLOYMENT_ID_CLAIM) or launch_data.get('deployment_id') or '')


def _get_client_id(launch_data):
    return (
        str(launch_data.get('client_id') or '')
        or _first_audience(launch_data.get('aud'))
        or str(launch_data.get('azp') or '')
        or str(launch_data.get('oauth_consumer_key') or '')
    )


def _get_registration(issuer, client_id):
    if not issuer or not client_id:
        return None
    normalized_issuer = normalize_platform_issuer(issuer)
    issuer_candidates = {issuer, normalized_issuer}
    if normalized_issuer:
        issuer_candidates.add(f"{normalized_issuer}/")
    return (
        LTIPlatformRegistration.objects
        .filter(issuer__in=issuer_candidates, client_id=client_id, is_active=True)
        .order_by('-updated_at', '-id')
        .first()
    )


def _get_target_link_course_id(launch_data):
    target_link_uri = launch_data.get(LTI_TARGET_LINK_URI_CLAIM) or launch_data.get('target_link_uri') or ''
    if not target_link_uri:
        return ''
    try:
        query = parse_qs(urlparse(target_link_uri).query)
    except Exception:
        return ''
    return (query.get('course_id') or query.get('custom_course_id') or [''])[0]


def _get_course_instance_id(request, launch_data):
    custom_claim = _claim_dict(launch_data, LTI_CUSTOM_CLAIM)
    return (
        launch_data.get('custom_course_id')
        or launch_data.get('custom_modulearn_course_id')
        or custom_claim.get('course_id')
        or custom_claim.get('custom_course_id')
        or custom_claim.get('modulearn_course_id')
        or request.GET.get('course_id')
        or _get_target_link_course_id(launch_data)
    )


def _get_lms_context_ids(launch_data):
    context = _claim_dict(launch_data, LTI_CONTEXT_CLAIM)
    resource_link = _claim_dict(launch_data, LTI_RESOURCE_LINK_CLAIM)
    return {
        'context_id': (
            context.get('id')
            or launch_data.get('context_id')
            or launch_data.get('custom_canvas_course_id')
            or ''
        ),
        'resource_link_id': (
            resource_link.get('id')
            or launch_data.get('resource_link_id')
            or launch_data.get('custom_canvas_assignment_id')
            or ''
        ),
    }


def _identity_issuer(launch_data):
    issuer = normalize_platform_issuer(launch_data.get('iss') or '')
    return issuer or f"lti1p1:{launch_data.get('oauth_consumer_key') or 'unknown'}"


def _safe_launch_snapshot(launch_data):
    redacted = {}
    for key, value in launch_data.items():
        if key in {'id_token', 'oauth_signature'}:
            redacted[key] = '[redacted]'
        elif isinstance(value, (str, int, float, bool, list, dict)) or value is None:
            redacted[key] = value
        else:
            redacted[key] = str(value)
    return redacted


def _upsert_lti_identity(user, launch_data, subject):
    issuer = _identity_issuer(launch_data)
    client_id = _get_client_id(launch_data)
    deployment_id = _get_deployment_id(launch_data)
    registration = _get_registration(issuer, client_id)
    identity, _ = LTIUserIdentity.objects.update_or_create(
        issuer=issuer,
        client_id=client_id,
        subject=subject,
        defaults={
            'user': user,
            'platform_registration': registration,
            'deployment_id': deployment_id,
            'last_launch_data': _safe_launch_snapshot(launch_data),
        }
    )
    return identity

def process_launch_data(request, launch_data):
    """Process launch data common to both LTI 1.1 and 1.3"""
    # Extract user identifiers with fallbacks
    platform_user_id = str(
        launch_data.get('sub') or  # LTI 1.3 user ID
        launch_data.get('user_id') or  # LTI 1.1 user ID
        launch_data.get('custom_canvas_user_id') or  # Canvas-specific user ID
        ''
    )

    if not platform_user_id:
        logger.error("No user identifier found in launch data")
        return HttpResponse('Missing user identifier in launch data.', status=400)

    issuer = _identity_issuer(launch_data)
    client_id = _get_client_id(launch_data)
    deployment_id = _get_deployment_id(launch_data)

    email = normalize_email_address(
        launch_data.get('email') or  # LTI 1.3 email
        launch_data.get('lis_person_contact_email_primary')  # LTI 1.1 email
    )

    identity = (
        LTIUserIdentity.objects
        .filter(issuer=issuer, client_id=client_id, subject=platform_user_id)
        .select_related('user')
        .order_by('-last_seen_at', '-id')
        .first()
    )
    user = identity.user if identity else None

    if user is None and launch_data.get('lti_version_major') == '1.1':
        user = User.objects.filter(canvas_user_id=platform_user_id).order_by('id').first()

    email_owner = find_user_by_email(email)
    if user is None:
        user = email_owner

    created = user is None
    should_store_canvas_id = (
        launch_data.get('lti_version_major') == '1.1'
        or ('iss' not in launch_data and launch_data.get('user_id'))
        or 'canvas' in issuer.lower()
        or launch_data.get('custom_canvas_user_id')
    )

    if created:
        username = (
            unique_username_for_email(email)
            if email
            else unique_username_from_base(f"lti-{platform_user_id}")
        )
        create_kwargs = {
            'username': username,
            'email': email,
            'first_name': launch_data.get('given_name') or launch_data.get('lis_person_name_given', ''),
            'last_name': launch_data.get('family_name') or launch_data.get('lis_person_name_family', ''),
        }
        if should_store_canvas_id:
            create_kwargs['canvas_user_id'] = platform_user_id
        user = User.objects.create_user(
            **create_kwargs
        )
    else:
        update_fields = []
        if should_store_canvas_id and not user.canvas_user_id:
            user.canvas_user_id = platform_user_id
            update_fields.append('canvas_user_id')
        if email and user.email != email and (email_owner is None or email_owner.pk == user.pk):
            user.email = email
            update_fields.append('email')
        if update_fields:
            user.save(update_fields=update_fields)

    _upsert_lti_identity(user, launch_data, platform_user_id)

    # Update user roles
    roles = _get_roles(launch_data)
    apply_lti_roles(user, roles)

    # Log the user in before trying to access enrollments
    # Use ModelBackend since LTI users are created directly, not authenticated through a backend
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')

    # Store LTI session data
    request.session['lti_launch_data'] = launch_data
    request.session['canvas_user_id'] = platform_user_id
    request.session['lti_platform_user_id'] = platform_user_id
    request.session['lti_issuer'] = issuer
    request.session['lti_client_id'] = client_id
    request.session['lti_deployment_id'] = deployment_id
    request.session['is_lti_launch'] = True
    
    # Get the course session ID
    instance_id = _get_course_instance_id(request, launch_data)
    
    if instance_id:
        try:
            course_instance = CourseInstance.objects.get(
                id=instance_id,
                active=True
            )
            
            # Update LMS context info FIRST
            lms_context = _get_lms_context_ids(launch_data)
            canvas_course_id = launch_data.get('custom_canvas_course_id') or lms_context['context_id']
            canvas_assignment_id = launch_data.get('custom_canvas_assignment_id') or lms_context['resource_link_id']
            logger.info(
                "LTI launch context: issuer=%s client_id=%s deployment=%s context_id=%s resource_link_id=%s",
                issuer, client_id, deployment_id, canvas_course_id, canvas_assignment_id
            )
            
            if canvas_course_id and canvas_assignment_id:
                course_instance.canvas_course_id = canvas_course_id
                course_instance.canvas_assignment_id = canvas_assignment_id
                course_instance.lis_outcome_service_url = launch_data.get('lis_outcome_service_url')
                logger.info("Stored LTI context identifiers for instance %s", course_instance.id)
                course_instance.save(update_fields=[
                    'canvas_course_id',
                    'canvas_assignment_id',
                    'lis_outcome_service_url',
                ])
            
            # Then handle instructor/student specific logic
            if user.is_instructor:
                course_instance.instructors.add(user)
            elif user.is_student:
                existing_enrollment = Enrollment.objects.filter(
                    student=user,
                    course_instance=course_instance,
                ).first()
                if not existing_enrollment or not existing_enrollment.active:
                    try:
                        ensure_session_student_capacity(course_instance)
                    except CapacityLimitError as error:
                        logger.warning("LTI enrollment capacity limit hit for instance %s: %s", course_instance.id, str(error))
                        return HttpResponse(str(error), status=403)
                enrollment, created = Enrollment.objects.get_or_create(
                    student=user,
                    course_instance=course_instance,
                    defaults={'active': True}
                )
                if not enrollment.active:
                    enrollment.active = True
                    enrollment.save(update_fields=['active'])
                
                # Get or create CourseProgress (signal should create it, but handle race condition)
                course_progress, _ = CourseProgress.objects.get_or_create(
                    enrollment=enrollment
                )
                # Save LTI credentials for grade passback
                lis_result_sourcedid = launch_data.get('lis_result_sourcedid')
                if lis_result_sourcedid:
                    course_progress.lis_result_sourcedid = lis_result_sourcedid
                    course_progress.save(update_fields=['lis_result_sourcedid'])
                    logger.info(f"Saved lis_result_sourcedid for enrollment {enrollment.id}: {lis_result_sourcedid[:20]}...")
                else:
                    logger.warning(f"No lis_result_sourcedid in launch data for enrollment {enrollment.id}")
            
            return redirect('courses:course_detail', instance_id=course_instance.id)
        except CourseInstance.DoesNotExist:
            logger.error(f"Course instance {instance_id} not found")
    
    # If no instance_id or course not found, continue with normal launch flow
    # User is already logged in above, no need to log in again
    logger.info(
        "Successfully logged in LTI user: email=%s issuer=%s client_id=%s subject=%s",
        user.email, issuer, client_id, platform_user_id
    )

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
    course_id = request.GET.get('course_id') or request.GET.get('custom_course_id')
    launch_url = f"{domain}{prefixed_path('/lti/launch/')}"
    if course_id:
        launch_url = f"{launch_url}?course_id={escape(str(course_id), quote=True)}"
    icon_url = f"{domain}{settings.STATIC_URL}img/logo_128.png"
    
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
    <cartridge_basiclti_link 
        xmlns="http://www.imsglobal.org/xsd/imslticc_v1p0"
        xmlns:blti="http://www.imsglobal.org/xsd/imsbasiclti_v1p0"
        xmlns:lticm="http://www.imsglobal.org/xsd/imslticm_v1p0"
        xmlns:lticp="http://www.imsglobal.org/xsd/imslticp_v1p0"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.imsglobal.org/xsd/imslticc_v1p0 http://www.imsglobal.org/xsd/imslticc_v1p0.xsd">
        <blti:title>{escape(settings.LTI_TOOL_CONFIG['title'])}</blti:title>
        <blti:description>{escape(settings.LTI_TOOL_CONFIG['description'])}</blti:description>
        <blti:launch_url>{launch_url}</blti:launch_url>
        <blti:secure_launch_url>{launch_url}</blti:secure_launch_url>
        <blti:icon>{escape(icon_url, quote=True)}</blti:icon>
        <blti:custom>
            <lticm:property name="course_id">{escape(str(course_id or ''), quote=True)}</lticm:property>
            <lticm:property name="custom_course_id">{escape(str(course_id or ''), quote=True)}</lticm:property>
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


@login_required
def lti_setup_details(request):
    """Return copyable LTI setup URLs for an instructor-owned course session."""
    course_instance_id = request.GET.get('course_id') or request.GET.get('course_instance_id')
    if course_instance_id:
        try:
            course_instance = CourseInstance.objects.get(id=course_instance_id, active=True)
        except CourseInstance.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Course session not found.'}, status=404)
        if (
            not request.user.is_staff
            and not course_instance.instructors.filter(id=request.user.id).exists()
            and not (
                course_instance.course_id
                and course_instance.course.instructors.filter(id=request.user.id).exists()
            )
        ):
            return JsonResponse({'success': False, 'error': 'You do not manage this course session.'}, status=403)

    return JsonResponse({
        'success': True,
        'setup': lti_setup_payload(request, course_instance_id=course_instance_id),
    })


@login_required
@require_POST
def lti13_platform_registration(request):
    """Create or update an LTI 1.3 platform registration supplied by an LMS admin."""
    if not (request.user.is_staff or getattr(request.user, 'is_instructor', False)):
        return JsonResponse({'success': False, 'error': 'Only instructors can manage LTI registrations.'}, status=403)

    try:
        data = json.loads(request.body.decode('utf-8') or '{}') if request.body else request.POST
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON payload.'}, status=400)

    def clean(name):
        value = data.get(name, '')
        return str(value).strip() if value is not None else ''

    deployment_raw = data.get('deployment_ids') or data.get('deployment_id') or ''
    if isinstance(deployment_raw, list):
        deployment_ids = [str(item).strip() for item in deployment_raw if str(item).strip()]
    else:
        deployment_ids = [item.strip() for item in str(deployment_raw).replace('\n', ',').split(',') if item.strip()]

    required = {
        'name': clean('name'),
        'issuer': normalize_platform_issuer(clean('issuer')),
        'client_id': clean('client_id'),
        'auth_login_url': clean('auth_login_url'),
        'auth_token_url': clean('auth_token_url'),
        'key_set_url': clean('key_set_url'),
    }
    missing = [label for label, value in required.items() if not value]
    if not deployment_ids:
        missing.append('deployment_id')
    if missing:
        return JsonResponse({
            'success': False,
            'error': f"Missing required field(s): {', '.join(missing)}.",
        }, status=400)

    platform = clean('platform') or LTIPlatformRegistration.PLATFORM_OTHER
    valid_platforms = {choice[0] for choice in LTIPlatformRegistration.PLATFORM_CHOICES}
    if platform not in valid_platforms:
        platform = LTIPlatformRegistration.PLATFORM_OTHER

    registration, created = LTIPlatformRegistration.objects.update_or_create(
        issuer=required['issuer'],
        client_id=required['client_id'],
        defaults={
            'name': required['name'],
            'platform': platform,
            'deployment_ids': deployment_ids,
            'auth_login_url': required['auth_login_url'],
            'auth_token_url': required['auth_token_url'],
            'key_set_url': required['key_set_url'],
            'auth_audience': clean('auth_audience') or required['auth_token_url'],
            'is_active': True,
            'notes': clean('notes'),
        },
    )

    return JsonResponse({
        'success': True,
        'created': created,
        'registration': {
            'id': registration.id,
            'name': registration.name,
            'platform': registration.platform,
            'issuer': registration.issuer,
            'client_id': registration.client_id,
            'deployment_ids': registration.deployment_id_list(),
        },
    })
