from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import (
    Course,
    CourseInstance,
    CourseProgress,
    Enrollment,
    EnrollmentCode,
    Module,
    ModuleAccessLog,
    ModuleForm,
    ModuleFormAnswer,
    ModuleFormQuestion,
    ModuleFormSubmission,
    ModuleProgress,
    StudentScore,
    CaliperEvent,
    Unit,
)
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
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
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
from django.db import models, transaction
from modulearn.integrations.course_authoring import build_course_export_url
from modulearn.learning.selectors.courses import build_course_detail_context
from modulearn.learning.services.access_rules import (
    build_unlock_rule,
    evaluate_module_access,
    evaluate_unit_access,
    log_module_access,
    next_order_for_unit,
    next_order_for_module,
    sync_module_progress_for_course,
)
from modulearn.learning.services.progress import apply_progress_snapshot, record_module_launch
from modulearn.core.roles import get_user_role_snapshot

User = get_user_model()

# Configure logging
logger = logging.getLogger(__name__)

def force_https_url(url: str) -> str:
    """
    Convert http:// URLs to https://.
    This intentionally avoids the internal /proxy/ rewriting for module iframes.
    """
    if not url:
        return url
    try:
        u = urlparse(url)
        if u.scheme == 'http':
            return urlunparse(('https', u.netloc, u.path, u.params, u.query, u.fragment))
        return url
    except Exception:
        return url

def to_path_style_proxy(url: str) -> str:
    """Convert URL to path-style proxy format for iframe src."""
    from urllib.parse import urlparse
    u = urlparse(url)
    # Only allow http here
    if u.scheme != "http":
        return url   # for https, keep direct
    # guard host
    if u.hostname not in getattr(settings, "PROXY_ALLOWED_HOSTS", set()):
        return url
    # Build /proxy/http/<host>/<path>?<query>
    path = u.path.lstrip('/')
    base = f"/proxy/http/{u.hostname}/{path}"
    return f"{base}?{u.query}" if u.query else base


def _is_course_instructor(user, course_instance):
    return course_instance.instructors.filter(id=user.id).exists()


def _get_active_enrollment(user, course_instance):
    return Enrollment.objects.filter(student=user, course_instance=course_instance, active=True).first()


def _parse_bool(value):
    return str(value).lower() in {'1', 'true', 'yes', 'on'}


def _user_can_access_module(user, course_instance, module):
    is_instructor = _is_course_instructor(user, course_instance)
    enrollment = _get_active_enrollment(user, course_instance)
    if is_instructor:
        return True, ''
    if not enrollment:
        return False, "You are not enrolled in this course session."
    unit_state = evaluate_unit_access(module.unit, enrollment)
    module_state = evaluate_module_access(module, enrollment, unit_state=unit_state)
    return module_state.can_access, module_state.reason


def _module_rule_context(course):
    return [
        {
            "unit": unit,
            "modules": list(unit.modules.all()),
        }
        for unit in course.units.prefetch_related("modules").all()
    ]

@login_required
def course_list(request):
    """
    Legacy course index entry point.
    Role-specific dashboards now own course/session cards.
    """
    role_snapshot = get_user_role_snapshot(request.user)
    if role_snapshot["effective_is_instructor"] and not role_snapshot["effective_is_student"]:
        return redirect("dashboard:instructor_dashboard")
    return redirect("dashboard:student_dashboard")

@login_required
def course_detail(request, instance_id):
    """
    Displays details of a specific course instance and related instances 
    that the user has access to.
    """
    course_instance = get_object_or_404(CourseInstance, id=instance_id)
    context = build_course_detail_context(request.user, course_instance)

    # Handle enrollment POST request
    if request.method == 'POST' and request.user.is_student:
        if not context['is_enrolled']:
            Enrollment.objects.create(
                student=request.user, 
                course_instance=course_instance
            )
            messages.success(request, f'You have been enrolled in {course_instance}')
            return redirect('courses:course_detail', instance_id=instance_id)

    return render(request, 'courses/course_detail.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def course_configuration(request, instance_id):
    course_instance = get_object_or_404(CourseInstance, id=instance_id)
    if not _is_course_instructor(request.user, course_instance):
        raise PermissionDenied("Only instructors can configure this course.")

    course = course_instance.course
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "update_structure":
                _update_course_structure_controls(request, course)
                messages.success(request, "Course visibility and locking controls were updated.")
            elif action == "add_unit":
                _create_manual_unit(request, course)
                messages.success(request, "Unit added to the course structure.")
            elif action == "add_module":
                _create_custom_module(request, course)
                messages.success(request, "Module added to the course structure.")
            else:
                messages.error(request, "Unknown course configuration action.")
        except Exception as exc:
            logger.error("Course configuration update failed: %s", exc, exc_info=True)
            messages.error(request, str(exc))
        return redirect("courses:course_configuration", instance_id=course_instance.id)

    context = {
        "course": course,
        "course_instance": course_instance,
        "unit_groups": _module_rule_context(course),
        "module_types": Module.MODULE_TYPE_CHOICES[1:],
        "question_types": ModuleFormQuestion.TYPE_CHOICES,
    }
    return render(request, "courses/course_configuration.html", context)


def _update_course_structure_controls(request, course):
    for unit in course.units.all():
        prefix = f"unit_{unit.id}"
        unit.title = request.POST.get(f"{prefix}_title", unit.title).strip() or unit.title
        unit.description = request.POST.get(f"{prefix}_description", unit.description)
        unit.order = int(request.POST.get(f"{prefix}_order") or unit.order or 0)
        unit.is_visible = _parse_bool(request.POST.get(f"{prefix}_visible"))
        unit.is_locked = _parse_bool(request.POST.get(f"{prefix}_locked"))
        unit.unlock_rule = build_unlock_rule(
            request.POST.get(f"{prefix}_rule_type"),
            request.POST.get(f"{prefix}_rule_target"),
        )
        unit.save(update_fields=["title", "description", "order", "is_visible", "is_locked", "unlock_rule"])

        for module in unit.modules.all():
            module_prefix = f"module_{module.id}"
            module.title = request.POST.get(f"{module_prefix}_title", module.title).strip() or module.title
            module.description = request.POST.get(f"{module_prefix}_description", module.description)
            module.order = int(request.POST.get(f"{module_prefix}_order") or module.order or 0)
            module.is_visible = _parse_bool(request.POST.get(f"{module_prefix}_visible"))
            module.is_locked = _parse_bool(request.POST.get(f"{module_prefix}_locked"))
            module.unlock_rule = build_unlock_rule(
                request.POST.get(f"{module_prefix}_rule_type"),
                request.POST.get(f"{module_prefix}_rule_target"),
            )
            module.save(update_fields=[
                "title",
                "description",
                "order",
                "is_visible",
                "is_locked",
                "unlock_rule",
            ])


def _create_manual_unit(request, course):
    title = (request.POST.get("unit_title") or "").strip()
    if not title:
        raise ValueError("Unit title is required.")

    Unit.objects.create(
        course=course,
        title=title,
        description=request.POST.get("unit_description", ""),
        order=int(request.POST.get("unit_order") or next_order_for_unit(course)),
        is_visible=True,
        is_locked=False,
        unlock_rule={},
    )


def _create_custom_module(request, course):
    unit_id = request.POST.get("unit_id")
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    module_type = request.POST.get("module_type")
    valid_types = {choice[0] for choice in Module.MODULE_TYPE_CHOICES}
    if module_type not in valid_types or module_type == Module.MODULE_TYPE_IMPORTED:
        raise ValueError("Choose a valid manually-authored module type.")

    title = (request.POST.get("title") or "").strip()
    if not title:
        raise ValueError("Module title is required.")

    supported_protocols = ['splice'] if module_type == Module.MODULE_TYPE_SPLICE_SMART_CONTENT else []

    module = Module.objects.create(
        unit=unit,
        title=title,
        description=request.POST.get("description", ""),
        module_type=module_type,
        order=int(request.POST.get("order") or next_order_for_module(unit)),
        content_url=request.POST.get("content_url") or None,
        content_file=request.FILES.get("content_file"),
        is_visible=True,
        is_locked=False,
        supported_protocols=supported_protocols,
    )

    if module_type == Module.MODULE_TYPE_FORM:
        module_form = ModuleForm.objects.create(
            module=module,
            instructions=request.POST.get("form_instructions", ""),
            allow_resubmission=_parse_bool(request.POST.get("allow_resubmission")),
            submit_button_label=request.POST.get("submit_button_label") or "Submit",
        )
        _create_form_questions(module_form, request.POST.get("questions_json") or "[]")

    sync_module_progress_for_course(module)
    for course_progress in CourseProgress.objects.filter(enrollment__course_instance__course=course):
        course_progress.update_progress()
    return module


def _create_form_questions(module_form, questions_json):
    try:
        questions = json.loads(questions_json)
    except json.JSONDecodeError as exc:
        raise ValueError("The form questions could not be parsed.") from exc

    valid_types = {choice[0] for choice in ModuleFormQuestion.TYPE_CHOICES}
    for index, question in enumerate(questions, start=1):
        prompt = (question.get("prompt") or "").strip()
        question_type = question.get("question_type")
        if not prompt or question_type not in valid_types:
            continue
        options = question.get("options") or []
        if question_type in {ModuleFormQuestion.TYPE_SINGLE_CHOICE, ModuleFormQuestion.TYPE_MULTIPLE_CHOICE}:
            options = [str(option).strip() for option in options if str(option).strip()]
        ModuleFormQuestion.objects.create(
            form=module_form,
            prompt=prompt,
            help_text=(question.get("help_text") or "").strip(),
            question_type=question_type,
            required=bool(question.get("required", True)),
            order=index * 10,
            options=options,
            likert_min_label=(question.get("likert_min_label") or "Strongly disagree").strip(),
            likert_max_label=(question.get("likert_max_label") or "Strongly agree").strip(),
        )

@login_required
def module_detail(request, instance_id, unit_id, module_id):
    """
    Legacy module detail entry point.
    Keep the route for compatibility, but send users directly to the launch flow.
    """
    course_instance = get_object_or_404(CourseInstance, id=instance_id)
    course = course_instance.course
    
    # Check if user has access to this course instance
    if not (course_instance.instructors.filter(id=request.user.id).exists() or 
            course_instance.enrollments.filter(student=request.user).exists()):
        raise PermissionDenied("You don't have access to this course instance.")
    
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    module = get_object_or_404(Module, id=module_id, unit=unit)
    allowed, reason = _user_can_access_module(request.user, course_instance, module)
    if not allowed:
        if not _is_course_instructor(request.user, course_instance):
            log_module_access(request.user, module, course_instance, event_type=ModuleAccessLog.EVENT_UNLOCK_DENIED)
        messages.error(request, reason or "That module is locked.")
        return redirect("courses:course_detail", instance_id=course_instance.id)

    return redirect(
        'courses:launch_iframe_module',
        instance_id=course_instance.id,
        module_id=module.id,
    )

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
    course_instance = get_object_or_404(CourseInstance, id=instance_id)
    module = get_object_or_404(Module, id=module_id, unit__course=course_instance.course)
    course = course_instance.course  # Get course from course_instance
    
    # Check if user has access to this module
    is_instructor = course_instance.instructors.filter(id=request.user.id).exists()
    is_enrolled = Enrollment.objects.filter(student=request.user, course_instance=course_instance).exists()
    
    if not (is_instructor or is_enrolled):
        return HttpResponseForbidden("You don't have access to this module")

    allowed, reason = _user_can_access_module(request.user, course_instance, module)
    if not allowed:
        log_module_access(request.user, module, course_instance, event_type=ModuleAccessLog.EVENT_UNLOCK_DENIED)
        messages.error(request, reason or "That module is locked.")
        return redirect("courses:course_detail", instance_id=course_instance.id)
    
    # Use the get_or_create_progress class method instead of direct get_or_create
    module_progress, created = ModuleProgress.get_or_create_progress(
        user=request.user,
        module=module,
        course_instance=course_instance
    )
    if not is_instructor:
        record_module_launch(module_progress, source='iframe_launch')
        log_module_access(request.user, module, course_instance, event_type=ModuleAccessLog.EVENT_LAUNCH)

    if module.module_type == Module.MODULE_TYPE_FORM:
        return _handle_form_module(request, course_instance, module, module_progress, is_instructor)

    if module.module_type == Module.MODULE_TYPE_FILE:
        if not is_instructor:
            log_module_access(request.user, module, course_instance, event_type=ModuleAccessLog.EVENT_DOWNLOAD)
        return render(request, "courses/module_resource.html", {
            "module": module,
            "course_instance": course_instance,
            "progress": module_progress,
            "resource_kind": "file",
        })

    if module.module_type == Module.MODULE_TYPE_EXTERNAL_LINK:
        return render(request, "courses/module_resource.html", {
            "module": module,
            "course_instance": course_instance,
            "progress": module_progress,
            "resource_kind": "external_link",
        })
    
    # Get the module's content URL and selected protocol
    content_url = module.content_url
    original_content_url = content_url  # Keep original for logging
    selected_protocol = module.select_launch_protocol()
    
    logger.info(f"Module {module.id}: Original content_url: {original_content_url}")
    logger.info(f"Module {module.id}: Provider ID: {module.provider_id}")
    
    # Parse URL for LTI parameters
    parsed_url = urlparse(content_url) if content_url else None
    query_params = parse_qs(parsed_url.query) if parsed_url else {}
    
    # Extract tool and sub parameters from URL (common in LTI launch URLs)
    url_tool = query_params.get('tool', [''])[0]
    url_sub = query_params.get('sub', [''])[0]
    
    logger.info(f"Module {module.id}: Parsed URL - tool={url_tool}, sub={url_sub}, path={parsed_url.path if parsed_url else 'None'}")
    
    # SPECIAL HANDLING: CodeCheck exercises should load directly from their activity URL
    # instead of going through LTI launch. Detect CodeCheck by provider_id or tool parameter.
    is_codecheck = (
        module.provider_id and module.provider_id.lower() == 'codecheck'
    ) or (
        url_tool and url_tool.lower() == 'codecheck'
    )
    
    # SPECIAL HANDLING: JSVEE URL transformation
    # Transform JSVEE URLs from: /pitt/jsvee/jsvee-python/ae?example-id=ae_adl_variables
    # To: /html/jsvee/jsvee-python/ae_adl_variables
    # Also handles: /acos/pitt/jsvee/jsvee-python/ae?example-id=...
    if content_url and '/jsvee/jsvee-python/ae?' in content_url and 'example-id=' in content_url:
        parsed = urlparse(content_url)
        query_params = parse_qs(parsed.query)
        example_id = query_params.get('example-id', [None])[0]
        if example_id:
            # Build new path: replace .../jsvee/jsvee-python/ae?example-id=... with /html/jsvee/jsvee-python/...
            # Handle both /pitt/jsvee/... and /acos/pitt/jsvee/... patterns
            new_path = f"/html/jsvee/jsvee-python/{example_id}"
            content_url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                new_path,
                parsed.params,
                '',  # Remove query string
                parsed.fragment
            ))
            logger.info(f"Module {module.id}: Transformed JSVEE URL from {parsed.path}?{parsed.query} to: {content_url}")
    
    # SPECIAL HANDLING: Parson's Problems URL transformation
    # Transform from: http://adapt2.sis.pitt.edu/acos/pitt/jsparsons/jsparsons-python/ps?example-id=ps_python_for_odd_or_even
    # To: https://acos.cs.vt.edu/html/jsparsons/jsparsons-python/ps_python_for_odd_or_even
    if content_url and '/jsparsons/jsparsons-python/ps?' in content_url and 'example-id=' in content_url:
        parsed = urlparse(content_url)
        query_params = parse_qs(parsed.query)
        example_id = query_params.get('example-id', [None])[0]
        if example_id:
            # Build new URL: change to https://acos.cs.vt.edu/html/jsparsons/jsparsons-python/{example_id}
            new_path = f"/html/jsparsons/jsparsons-python/{example_id}"
            content_url = urlunparse((
                'https',  # Always use https
                'acos.cs.vt.edu',  # Always use acos.cs.vt.edu
                new_path,
                '',  # No params
                '',  # Remove query string
                ''   # No fragment
            ))
            logger.info(f"Module {module.id}: Transformed Parson's Problems URL from {parsed.geturl()} to: {content_url}")
    
    # SPECIAL HANDLING: WebEx exercises URL transformation
    # Transform from: http://adapt2.sis.pitt.edu/web_ex_NV0FGdaHzy/Dissection2?act=pyt4.7&svc=progvis&sid=demo
    # To: http://adapt2.sis.pitt.edu/web_ex_NV0FGdaHzy/Dissection2?act=pyt4.1&svc=progvis
    # Also handles URLs with additional parameters (grp, usr, sid, cid) - removes them
    if content_url and '/web_ex_' in content_url:
        parsed = urlparse(content_url)
        query_params = parse_qs(parsed.query)
        
        # Check if this is a WebEx exercise (has act and svc parameters)
        if 'act' in query_params and 'svc' in query_params:
            # Change act parameter: pyt4.7 -> pyt4.1 (or keep other act values as-is if not pyt4.7)
            act_value = query_params.get('act', [''])[0]
            if act_value.startswith('pyt4.'):
                # Change to pyt4.1
                query_params['act'] = ['pyt4.1']
            # Keep only act and svc parameters, remove all others (grp, usr, sid, cid, etc.)
            new_query_params = {
                'act': query_params['act'],
                'svc': query_params['svc']
            }
            
            # Rebuild URL with only act and svc parameters
            new_query = urlencode(new_query_params, doseq=True)
            content_url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment
            ))
            logger.info(f"Module {module.id}: Transformed WebEx URL from {parsed.geturl()} to: {content_url}")
    
    if is_codecheck:
        # CodeCheck: Simply construct the direct URL and load it in iframe
        # Format: https://codecheck.io/files/wiley/{module_name}
        module_name = url_sub if url_sub else module.title
        if module_name:
            content_url = f"https://codecheck.io/files/wiley/{module_name}"
            logger.info(f"Module {module.id}: CodeCheck detected - constructing direct URL: {content_url}")
            # Re-parse the new URL
            parsed_url = urlparse(content_url)
            query_params = parse_qs(parsed_url.query) if parsed_url else {}
            # Use direct loading (no LTI)
            selected_protocol = 'splice'  # Use splice for direct loading with session params
            is_lti_launch_url = False
        else:
            logger.warning(f"Module {module.id}: CodeCheck detected but no module name available")
            selected_protocol = 'splice'
            is_lti_launch_url = False
    else:
        # Detect LTI launch URLs: URLs with ?tool=...&sub=... pattern pointing to /lti/launch
        # These should go through our LTI consumer, not be proxied directly
        is_lti_launch_url = (
            parsed_url and 
            '/lti/launch' in parsed_url.path and 
            url_tool and url_sub
        )
    
    # Detect if this is a PAWS-mediated URL (adapt2.sis.pitt.edu/lti/launch)
    # PAWS URLs should use our paws_* tool configs which route through PAWS
    # Skip this for CodeCheck since we're loading directly
    is_paws_url = False
    if not is_codecheck:
        is_paws_url = (
            parsed_url and 
            parsed_url.hostname and
            parsed_url.hostname in ('adapt2.sis.pitt.edu', 'pawscomp2.sis.pitt.edu', 'columbus.exp.sis.pitt.edu') and
            '/lti/launch' in parsed_url.path
        )
    
    # If no protocol set but URL looks like LTI launch, treat as LTI
    # Skip for CodeCheck since we're loading directly
    if not is_codecheck and selected_protocol is None and is_lti_launch_url:
        selected_protocol = 'lti'
        logger.info(f"Module {module.id}: Auto-detected LTI protocol from URL pattern")
    
    # For LTI protocol, extract the sub parameter for our LTI consumer
    lti_sub = url_sub if url_sub else None
    
    # Determine the LTI tool to use (not used for CodeCheck)
    lti_tool = None
    if not is_codecheck:
        if is_paws_url and url_tool:
            lti_tool = f"paws_{url_tool}"
            logger.info(f"Module {module.id}: PAWS-mediated tool detected, using '{lti_tool}'")
        else:
            lti_tool = url_tool if url_tool else module.provider_id
    elif is_paws_url and url_tool:
        lti_tool = f"paws_{url_tool}"
        logger.info(f"Module {module.id}: PAWS-mediated tool detected, using '{lti_tool}'")
    else:
        lti_tool = url_tool if url_tool else module.provider_id
    
    # For CodeCheck or SPLICE/PITT protocols: append session parameters directly to URL
    # This matches the working codebase pattern: activity_url + "&grp=...&usr=...&sid=...&cid=..."
    # EXCEPT for WebEx exercises - they should NOT have session parameters added
    use_proxy = False
    activity_url_with_params = content_url
    
    # Check if this is a WebEx exercise (should not have session parameters)
    is_webex = content_url and '/web_ex_' in content_url
    
    if content_url and (is_codecheck or selected_protocol in ('splice', 'pitt', None)) and not is_lti_launch_url and not is_webex:
        # Build session parameters matching the working codebase pattern
        # grp: group_name (or course_instance.id as fallback)
        grp = course_instance.group_name if course_instance and course_instance.group_name else (str(course_instance.id) if course_instance else 'default')
        # usr: username (activities expect username, not user.id)
        usr = request.user.username
        # sid: Django session key
        sid = request.session.session_key or ''
        # cid: course.id
        cid = str(course_instance.course.id) if course_instance and course_instance.course else ''
        
        # Parse the base URL and append parameters
        parsed = urlparse(content_url)
        existing_params = parse_qs(parsed.query)
        
        # Add session parameters (don't overwrite if already present)
        if 'grp' not in existing_params:
            existing_params['grp'] = [grp]
        if 'usr' not in existing_params:
            existing_params['usr'] = [usr]
        if 'sid' not in existing_params and sid:
            existing_params['sid'] = [sid]
        if 'cid' not in existing_params and cid:
            existing_params['cid'] = [cid]
        
        # Rebuild URL with all parameters
        new_query = urlencode(existing_params, doseq=True)
        activity_url_with_params = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
        
        logger.info(
            f"Module {module.id}: Built activity URL with session params: "
            f"grp={grp}, usr={usr}, sid={sid[:10]}..., cid={cid}"
        )
        
        # Force HTTPS for iframe embedding (no proxy rewriting)
        activity_url_with_params = force_https_url(activity_url_with_params)
    
    logger.info(f"Module {module.id} '{module.title}' selected protocol: {selected_protocol}")
    logger.info(f"Module {module.id} - Original content_url: {original_content_url}")
    logger.info(f"Module {module.id} - Final content_url: {content_url}")
    logger.info(f"Module {module.id} - Activity URL with params: {activity_url_with_params}")
    logger.info(f"Module {module.id} - Use proxy: {use_proxy}, Is LTI URL: {is_lti_launch_url}, Is CodeCheck: {is_codecheck}")
    
    # Check if tool is known to refuse iframe embedding
    refuses_iframe = False
    refuses_iframe_reason = ''
    if selected_protocol == 'lti' and lti_tool:
        from lti.config import get_tool_config
        tool_config = get_tool_config(lti_tool)
        if tool_config:
            refuses_iframe = tool_config.get('refuses_iframe', False)
            refuses_iframe_reason = tool_config.get('refuses_iframe_reason', '')
            if refuses_iframe:
                logger.warning(f"Module {module.id}: Tool '{lti_tool}' refuses iframe embedding: {refuses_iframe_reason}")
    
    # Generate iframe src based on protocol
    if selected_protocol == 'lti':
        # Route through our LTI consumer which handles OAuth signing
        # Include module_id so outcomes can update ModuleProgress
        grp_id = course_instance.id if course_instance else 'default'
        
        iframe_src = (
            f"{reverse('lti_launch')}?tool={lti_tool}&sub={lti_sub or content_url}"
            f"&usr={request.user.id}&grp={grp_id}&module_id={module.id}"
        )
        logger.info(
            f"LTI Launch URL generated: module={module.id}, tool={lti_tool}, "
            f"sub={lti_sub}, user={request.user.id}, instance={grp_id}"
        )
    else:
        # Use the URL with session parameters directly, forcing HTTPS if needed
        iframe_src = force_https_url(activity_url_with_params)
        logger.info(f"Module {module.id}: Final iframe_src (direct, https): {iframe_src}")

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
        'iframe_src': iframe_src,
        'refuses_iframe': refuses_iframe,
        'refuses_iframe_reason': refuses_iframe_reason,
    }
    
    response = render(request, 'courses/module_frame.html', context)
    response['X-Frame-Options'] = 'SAMEORIGIN'
    return response


def _handle_form_module(request, course_instance, module, module_progress, is_instructor):
    module_form = get_object_or_404(ModuleForm, module=module)
    enrollment = module_progress.enrollment
    questions = list(module_form.questions.all())
    existing_submission = None
    if enrollment:
        existing_submission = (
            ModuleFormSubmission.objects.filter(form=module_form, enrollment=enrollment)
            .prefetch_related("answers")
            .first()
        )

    if request.method == "POST" and not is_instructor:
        if existing_submission and not module_form.allow_resubmission:
            messages.info(request, "This form has already been submitted.")
            return redirect("courses:course_detail", instance_id=course_instance.id)

        answers_payload = {}
        missing_required = []
        for question in questions:
            field_name = f"question_{question.id}"
            if question.question_type == ModuleFormQuestion.TYPE_MULTIPLE_CHOICE:
                raw_value = request.POST.getlist(field_name)
                value = [item for item in raw_value if item]
                text_value = ", ".join(value)
            else:
                value = request.POST.get(field_name, "").strip()
                text_value = value

            if question.required and not value:
                missing_required.append(question.prompt)
            answers_payload[str(question.id)] = {
                "value": value,
                "text_value": text_value,
            }

        if missing_required:
            messages.error(request, "Please answer every required question.")
        else:
            submission = ModuleFormSubmission.objects.create(
                form=module_form,
                enrollment=enrollment,
                user=request.user,
                is_complete=True,
            )
            answer_rows = []
            for question in questions:
                answer_data = answers_payload[str(question.id)]
                answer_rows.append(ModuleFormAnswer(
                    submission=submission,
                    question=question,
                    value={"answer": answer_data["value"]},
                    text_value=answer_data["text_value"],
                ))
            ModuleFormAnswer.objects.bulk_create(answer_rows)
            apply_progress_snapshot(
                module_progress,
                source="module_form",
                progress=1.0,
                score=100.0,
                success=True,
                is_complete=True,
                payload=answers_payload,
                event_type="completion",
            )
            log_module_access(
                request.user,
                module,
                course_instance,
                event_type=ModuleAccessLog.EVENT_FORM_SUBMIT,
                metadata={"submission_id": submission.id},
            )
            messages.success(request, "Your response was submitted.")
            return redirect("courses:course_detail", instance_id=course_instance.id)

    return render(request, "courses/module_form.html", {
        "module": module,
        "course_instance": course_instance,
        "module_form": module_form,
        "questions": questions,
        "progress": module_progress,
        "existing_submission": existing_submission,
        "is_instructor": is_instructor,
    })

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

    # Get the module's content URL and selected protocol
    content_url = module.content_url
    selected_protocol = module.select_launch_protocol()
    
    # Parse URL for LTI parameters
    parsed_url = urlparse(content_url) if content_url else None
    query_params = parse_qs(parsed_url.query) if parsed_url else {}
    
    # Extract tool and sub parameters from URL (common in LTI launch URLs)
    url_tool = query_params.get('tool', [''])[0]
    url_sub = query_params.get('sub', [''])[0]
    
    # SPECIAL HANDLING: CodeCheck exercises - load directly from activity URL
    is_codecheck = (
        module.provider_id and module.provider_id.lower() == 'codecheck'
    ) or (
        url_tool and url_tool.lower() == 'codecheck'
    )
    
    if is_codecheck:
        # CodeCheck: Simply construct the direct URL and load it in iframe
        # Format: https://codecheck.io/files/wiley/{module_name}
        module_name = url_sub if url_sub else module.title
        if module_name:
            content_url = f"https://codecheck.io/files/wiley/{module_name}"
            logger.info(f"Preview module {module.id}: CodeCheck detected - constructing direct URL: {content_url}")
            # Re-parse the new URL
            parsed_url = urlparse(content_url)
            query_params = parse_qs(parsed_url.query) if parsed_url else {}
            # Use direct loading (no LTI)
            selected_protocol = 'splice'  # Use splice for direct loading with session params
            is_lti_launch_url_check = False
        else:
            logger.warning(f"Preview module {module.id}: CodeCheck detected but no module name available")
            selected_protocol = 'splice'
            is_lti_launch_url_check = False
    
    # Detect LTI launch URLs: URLs with ?tool=...&sub=... pattern pointing to /lti/launch
    # Skip this check for CodeCheck since we handle it above
    is_lti_launch_url_check = False
    if not is_codecheck:
        is_lti_launch_url_check = (
            parsed_url and 
            '/lti/launch' in parsed_url.path and 
            url_tool and url_sub
        )
    
    # Detect if this is a PAWS-mediated URL (adapt2.sis.pitt.edu/lti/launch)
    # Skip for CodeCheck since we handle it above
    is_paws_url = False
    if not is_codecheck:
        is_paws_url = (
            parsed_url and 
            parsed_url.hostname and
            parsed_url.hostname in ('adapt2.sis.pitt.edu', 'pawscomp2.sis.pitt.edu', 'columbus.exp.sis.pitt.edu') and
            '/lti/launch' in parsed_url.path
        )
    
    # If no protocol set but URL looks like LTI launch, treat as LTI
    # (Skip for CodeCheck since we've already set it)
    if not is_codecheck and selected_protocol is None and is_lti_launch_url_check:
        selected_protocol = 'lti'
        logger.info(f"Preview module {module.id}: Auto-detected LTI protocol from URL pattern")
    
    # For LTI protocol, extract the sub parameter for our LTI consumer
    lti_sub = url_sub if url_sub else None
    
    # Determine the LTI tool to use (not used for CodeCheck)
    lti_tool = None
    if not is_codecheck:
        if is_paws_url and url_tool:
            lti_tool = f"paws_{url_tool}"
            logger.info(f"Preview module {module.id}: PAWS-mediated tool detected, using '{lti_tool}'")
        else:
            lti_tool = url_tool if url_tool else module.provider_id
    
    # For CodeCheck or SPLICE/PITT protocols: append session parameters directly to URL
    # For preview mode, use minimal parameters since there's no course instance
    use_proxy = False
    activity_url_with_params = content_url
    
    if content_url and (is_codecheck or selected_protocol in ('splice', 'pitt', None)) and not is_lti_launch_url_check:
        # Build session parameters for preview (minimal since no course instance)
        # grp: 'preview' for instructor previews
        grp = 'preview'
        # usr: username
        usr = request.user.username
        # sid: Django session key
        sid = request.session.session_key or ''
        # cid: course.id if available
        cid = str(module.course.id) if module.course else ''
        
        # Parse the base URL and append parameters
        parsed = urlparse(content_url)
        existing_params = parse_qs(parsed.query)
        
        # Add session parameters (don't overwrite if already present)
        if 'grp' not in existing_params:
            existing_params['grp'] = [grp]
        if 'usr' not in existing_params:
            existing_params['usr'] = [usr]
        if 'sid' not in existing_params and sid:
            existing_params['sid'] = [sid]
        if 'cid' not in existing_params and cid:
            existing_params['cid'] = [cid]
        
        # Rebuild URL with all parameters
        new_query = urlencode(existing_params, doseq=True)
        activity_url_with_params = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
        
        logger.info(
            f"Preview module {module.id}: Built activity URL with session params: "
            f"grp={grp}, usr={usr}, sid={sid[:10]}..., cid={cid}"
        )
        
        # Force HTTPS for iframe embedding (no proxy rewriting)
        activity_url_with_params = force_https_url(activity_url_with_params)
    
    logger.info(f"Preview module {module.id} '{module.title}' selected protocol: {selected_protocol}")
    logger.debug(f"Preview - Protocol: {selected_protocol}, Content URL: {content_url}")
    logger.debug(f"Preview activity URL with params: {activity_url_with_params}")
    logger.debug(f"Preview use proxy for HTTP content: {use_proxy}, Is LTI URL: {is_lti_launch_url_check}")

    # Check if tool is known to refuse iframe embedding
    refuses_iframe = False
    refuses_iframe_reason = ''
    if selected_protocol == 'lti' and lti_tool:
        from lti.config import get_tool_config
        tool_config = get_tool_config(lti_tool)
        if tool_config:
            refuses_iframe = tool_config.get('refuses_iframe', False)
            refuses_iframe_reason = tool_config.get('refuses_iframe_reason', '')
            if refuses_iframe:
                logger.warning(f"Preview module {module.id}: Tool '{lti_tool}' refuses iframe embedding")
    
    # Generate iframe src based on protocol
    if selected_protocol == 'lti':
        # Route through our LTI consumer which handles OAuth signing
        # Include module_id but use 'preview' grp since no course instance
        
        iframe_src = (
            f"{reverse('lti_launch')}?tool={lti_tool}&sub={lti_sub or content_url}"
            f"&usr={request.user.id}&grp=preview&module_id={module.id}"
        )
        logger.info(f"LTI Preview URL generated: module={module.id}, tool={lti_tool}, sub={lti_sub}")
    else:
        # Use the URL with session parameters directly, forcing HTTPS if needed
        iframe_src = force_https_url(activity_url_with_params)

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
        'iframe_src': iframe_src,
        'refuses_iframe': refuses_iframe,
        'refuses_iframe_reason': refuses_iframe_reason,
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
                    lis_result_sourcedid=(score_data.get('id') or 'lti13-outcome')[:255]
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
                Enrollment.objects.create(
                    student=user,
                    course_instance=course_instance
                )
                enrollment_code.used = True
                enrollment_code.save(update_fields=['used'])
                
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

        allowed, reason = _user_can_access_module(request.user, course_instance, module)
        if not allowed:
            return JsonResponse({'error': reason or 'Module is locked'}, status=403)
        
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
    logger.info("Starting bulk enrollment process for course instance %s", course_instance_id)
    try:
        course_instance = CourseInstance.objects.get(id=course_instance_id)
        logger.info("Found course instance %s - %s", course_instance.id, course_instance.course.title)
        
        if request.user not in course_instance.instructors.all():
            logger.warning("User %s is not authorized for bulk enrollment on instance %s", request.user.username, course_instance.id)
            return JsonResponse({'error': 'Not authorized'}, status=403)
        
        data = json.loads(request.body)
        emails = data.get('emails', [])
        logger.debug("Processing emails for bulk enrollment: %s", emails)
        
        success_count = 0
        error_count = 0
        new_enrollments = []
        error_details = []
        
        for email in emails:
            try:
                validate_email(email)
                
                # Get or create user with email as username
                user, user_created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        'username': email,  # Use full email as username
                        'is_student': True
                    }
                )
                logger.debug("Bulk enrollment user %s: %s", "created" if user_created else "found", user.username)
                
                # Check enrollment
                enrollment, enrollment_created = Enrollment.objects.get_or_create(
                    student=user,
                    course_instance=course_instance,
                    defaults={'active': True}
                )
                
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
                else:
                    error_count += 1
                    error_details.append(f"{email}: Already enrolled in this course session")
                    
            except ValidationError as ve:
                logger.warning("Bulk enrollment validation error for %s: %s", email, str(ve))
                error_count += 1
                error_details.append(f"{email}: Invalid email format")
                continue
            except Exception as e:
                logger.error("Unexpected bulk enrollment error for %s: %s", email, str(e))
                error_count += 1
                error_details.append(f"{email}: {str(e)}")
                logger.error(f"Error enrolling {email}: {str(e)}", exc_info=True)
                continue
        
        logger.info(
            "Bulk enrollment process completed for instance %s: successes=%s errors=%s",
            course_instance.id,
            success_count,
            error_count,
        )
        
        return JsonResponse({
            'success': True,
            'success_count': success_count,
            'error_count': error_count,
            'error_details': error_details,
            'enrollments': new_enrollments
        })
        
    except CourseInstance.DoesNotExist:
        logger.warning("Course instance %s not found during bulk enrollment", course_instance_id)
        return JsonResponse({'error': 'Course instance not found'}, status=404)
    except Exception as e:
        logger.exception("Critical error in bulk enrollment for instance %s", course_instance_id)
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

@login_required
@require_GET
@ensure_csrf_cookie
def create_semester_course(request):
    logger.debug("Entered create_semester_course view")
    
    if not get_user_role_snapshot(request.user)["effective_is_instructor"]:
        logger.warning(f"Permission denied for user: {request.user}")
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    course_id = request.GET.get('course_id')
    logger.debug(f"Received course_id: {course_id}")

    # Render the template that handles the course creation process
    try:
        response = render(request, 'courses/create_semester_course.html', {
            'course_id': course_id,
            'course_export_url': build_course_export_url(course_id) if course_id else '',
            'create_course_url': reverse('courses:create_course'),
            'create_raw_session_url': reverse('courses:create_raw_course_session'),
            'instructor_dashboard_url': reverse('dashboard:instructor_dashboard'),
        })
        logger.debug("Successfully rendered create_semester_course.html")
        return response
    except Exception as e:
        logger.error(f"Error rendering template: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'Internal server error'}, status=500)


@login_required
@require_POST
def create_raw_course_session(request):
    if not get_user_role_snapshot(request.user)["effective_is_instructor"]:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON payload'}, status=400)

    course_title = (data.get("course_title") or "").strip() or "Untitled Course"
    group_name = (data.get("group_name") or "").strip() or "Session"
    course_description = (data.get("course_description") or "").strip()

    try:
        with transaction.atomic():
            course_id = f"manual-{uuid.uuid4().hex[:16]}"
            course = Course.objects.create(
                id=course_id,
                title=course_title,
                description=course_description,
            )
            course.instructors.add(request.user)

            instance = CourseInstance.objects.create(
                course=course,
                group_name=group_name,
            )
            instance.instructors.add(request.user)

            Unit.objects.create(
                course=course,
                title="Unit 1",
                description="",
                order=next_order_for_unit(course),
            )

        return JsonResponse({
            'success': True,
            'course_id': course.id,
            'instance_id': instance.id,
            'redirect_url': reverse('courses:course_configuration', kwargs={'instance_id': instance.id}),
        })
    except Exception as error:
        logger.exception("Failed to create custom course session for user %s", request.user.id)
        return JsonResponse({
            'success': False,
            'error': str(error) or 'Unable to create custom course session.'
        }, status=500)
