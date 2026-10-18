"""
LTI Tool Consumer Views

This module provides Django views for LTI 1.0/1.1 tool consumer functionality:
- /lti/tool-launch/ - Launch external LTI tools in iframes
- /lti/outcome/ - Receive outcome callbacks from tools

These endpoints are used to embed external learning tools (CodeCheck, CTAT, 
CodeWorkout, etc.) within ModuLearn and receive score reports back from them.

NOTE: This is separate from the Canvas LTI provider (lti/views.py) which handles
incoming launches FROM Canvas INTO ModuLearn.

INTEGRATION:
- Launches pass module_id so outcomes can update ModuleProgress
- Outcomes update both the UM service (ADAPT2) AND local ModuleProgress
- All operations are logged for debugging
"""
import os
import logging
import requests
import uuid
from urllib.parse import urlparse, parse_qs

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from lti.models import LTILaunchCache, LTIOutcomeLog
from lti.config import get_tool_config
from lti.services import (
    build_signed_lti_params,
    parse_outcome_xml,
    create_outcome_response,
    build_um_url,
    validate_identifier,
    generate_source_id,
)
from lti.config import get_tool_config, is_tool_configured, list_configured_tools

logger = logging.getLogger(__name__)

# Required query parameters for launch
REQUIRED_LAUNCH_PARAMS = ('tool', 'sub', 'usr', 'grp')

# UM Service URL (for outcome forwarding)
UM_SERVICE_URL = os.getenv('UM_SERVICE_URL', 'http://adapt2.sis.pitt.edu/aggregate2/UserActivity')

# TTL for launch cache entries (hours)
LTI_CACHE_TTL_HOURS = int(os.getenv('LTI_CACHE_TTL_HOURS', '24'))

# Whether to forward outcomes to UM service (can be disabled for testing)
LTI_FORWARD_TO_UM = os.getenv('LTI_FORWARD_TO_UM', 'true').lower() == 'true'


def _get_outcome_service_url(request) -> str:
    """
    Build the absolute URL for our outcome service endpoint.
    
    Uses request.build_absolute_uri() to respect reverse proxy headers.
    """
    from django.urls import reverse
    try:
        return request.build_absolute_uri(reverse('lti_outcome'))
    except Exception:
        # Fallback if URL resolution fails
        logger.warning("Failed to resolve lti_outcome URL, using fallback")
        return f"{request.scheme}://{request.get_host()}/lti/outcome/"


@transaction.atomic
def _update_module_progress(user_id: int, module_id: int, course_instance_id: int, 
                            score: float, source_id: str) -> bool:
    """
    Update ModuleProgress for a local module after receiving LTI outcome.
    
    Args:
        user_id: Django User.id
        module_id: Module.id
        course_instance_id: CourseInstance.id (can be None for previews)
        score: Normalized score (0.0-1.0)
        source_id: LTI source_id for logging
        
    Returns:
        True if progress was updated, False otherwise
    """
    try:
        from courses.models import Module, ModuleProgress, CourseInstance
        from accounts.models import User
        from modulearn.learning.services.progress import apply_progress_snapshot, module_accepts_scored_attempt
        
        # Get the user
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.warning(f"[LTI→Progress] User {user_id} not found for {source_id}")
            return False
        
        # Get the module
        try:
            module = Module.objects.get(id=module_id)
        except Module.DoesNotExist:
            logger.warning(f"[LTI→Progress] Module {module_id} not found for {source_id}")
            return False
        
        # A callback must identify its exact course session; never credit an
        # arbitrary enrollment when context is missing or stale.
        from modulearn.learning.services.tracking_context import enrolled_tracking_session
        if not course_instance_id:
            return False
        course_instance = enrolled_tracking_session(module.unit.course, user,
            {'course_instance_id': str(course_instance_id)})
        if not course_instance:
            return False
        import math
        if not math.isfinite(score) or not 0 <= score <= 1:
            return False
        progress, created = ModuleProgress.get_or_create_progress(
            user=user, module=module, course_instance=course_instance)
        progress = ModuleProgress.objects.select_for_update().get(pk=progress.pk)

        if not module_accepts_scored_attempt(progress):
            logger.info(
                f"[LTI→Progress] Ignoring resubmission for single-attempt module: user={user_id}, module={module_id}"
            )
            return False
        
        progress.attempts += 1
        progress.save(update_fields=['attempts', 'last_accessed'])
        # Preserve the best grade, while retaining every reported score in the
        # event payload, including unsuccessful and repeated submissions.
        best_score = max(progress.score or 0, score * 100.0)
        from modulearn.learning.services.progress import log_module_progress_event
        log_module_progress_event(progress, source='lti_outcome', event_type='outcome',
            score=score * 100, progress=score, success=score >= 0.7,
            payload={'source_id': source_id, 'attempt_score': score * 100.0})
        apply_progress_snapshot(
            progress, source='lti_outcome',
            progress=max(progress.progress or 0, score), score=best_score,
            success=best_score >= 70, is_complete=progress.is_complete or score >= 1,
            payload={'source_id': source_id, 'attempt_score': score * 100.0},
            event_type=None)
        return True

    except Exception as e:
        logger.exception(f"[LTI→Progress] Error updating progress for {source_id}: {e}")
        return False


@require_http_methods(["GET"])
def launch(request):
    """
    LTI Tool Launch endpoint.
    
    Takes query parameters and returns an HTML page containing an auto-submitting
    form that POSTs OAuth-signed LTI parameters to the tool provider.
    
    This endpoint is designed to be loaded in an iframe.
    
    Query Parameters:
        tool (required): Tool identifier (e.g., 'codecheck', 'ctat')
        sub (required): Activity/resource identifier
        usr (required): User identifier (Django user.id)
        grp (required): Group/context identifier (CourseInstance.id or 'default'/'preview')
        module_id (optional): Module.id for local progress tracking
        cid (optional): Course ID
        sid (optional): Session ID
        svc (optional): Service identifier
        step_explanation (optional): DBQA-specific parameter
    
    Returns:
        HTML page with auto-submitting form, or error response
    """
    logger.info("=" * 60)
    logger.info("[LTI Launch] Request received")
    logger.debug(f"[LTI Launch] Query params: {dict(request.GET)}")
    
    # Validate required parameters
    missing = [p for p in REQUIRED_LAUNCH_PARAMS if not request.GET.get(p)]
    if missing:
        logger.warning(f"[LTI Launch] ✗ Missing params: {missing}")
        return HttpResponseBadRequest(f"Missing required parameters: {', '.join(missing)}")
    
    # Extract parameters
    try:
        tool = validate_identifier(request.GET.get('tool', ''), 'tool', max_length=64)
        raw_sub = request.GET.get('sub', '')
        if tool in {'codecheck', 'paws_codecheck'} and raw_sub.startswith('https://') and len(raw_sub) <= 512:
            from lti.config import codecheck_url_modifier
            sub = codecheck_url_modifier('', raw_sub)
        else:
            sub = validate_identifier(raw_sub, 'sub', max_length=512)
        usr = validate_identifier(request.GET.get('usr', ''), 'usr', max_length=255)
        grp = validate_identifier(request.GET.get('grp', ''), 'grp', max_length=255)
    except ValueError as e:
        logger.warning(f"[LTI Launch] ✗ Validation error: {e}")
        return HttpResponseBadRequest(str(e))
    
    # Optional parameters
    cid = request.GET.get('cid', '')
    sid = request.GET.get('sid', '')
    svc = request.GET.get('svc', '')
    step_explanation = request.GET.get('step_explanation')
    
    # Module ID for local progress tracking
    module_id = request.GET.get('module_id')
    if module_id:
        try:
            module_id = int(module_id)
        except (ValueError, TypeError):
            logger.warning(f"[LTI Launch] Invalid module_id: {module_id}")
            module_id = None

    # Imported PAWS URLs remain portable: when registered locally, use our
    # signed launch and outcome endpoint instead of PAWS's hardcoded callback.
    if tool.startswith('paws_') and is_tool_configured(tool[5:]):
        tool = tool[5:]
    
    # Verify tool is configured
    if not is_tool_configured(tool):
        configured = list_configured_tools()
        logger.error(
            f"[LTI Launch] ✗ Tool '{tool}' not configured. "
            f"Configured tools: {configured}"
        )
        return HttpResponseBadRequest(
            f"Tool '{tool}' not configured. "
            f"Set env vars: {tool.upper()}_KEY, {tool.upper()}_SECRET, {tool.upper()}_LAUNCH"
        )
    
    # A signed launch is an authenticated operation, bound to this exact module
    # and course session. Query parameters must not impersonate another learner.
    from courses.models import Module
    from modulearn.learning.services.tracking_context import enrolled_tracking_session
    if not request.user.is_authenticated or usr != str(request.user.pk):
        return HttpResponseForbidden('Sign in as the launching user.')
    module = Module.objects.filter(pk=module_id).select_related('unit__course').first() if module_id else None
    if not module:
        return HttpResponseBadRequest('A valid module is required.')
    from lti.config import resolve_tool_name
    resource_params = parse_qs(urlparse(module.content_url or '').query)
    expected_sub = resource_params.get('sub', [module.content_url])[0]
    expected_tool = resource_params.get('tool', [module.provider_id])[0]
    if (module.select_launch_protocol() != 'lti' or sub != expected_sub
            or tool != resolve_tool_name(expected_tool)):
        return HttpResponseForbidden('The LTI activity does not match this module.')
    if grp == 'preview':
        if not module.unit.course.instructors.filter(pk=request.user.pk).exists():
            return HttpResponseForbidden('Instructor preview access required.')
    elif not enrolled_tracking_session(module.unit.course, request.user, {'course_instance_id': grp}):
        return HttpResponseForbidden('Activity enrollment not found.')
    source_id = 'ml-' + uuid.uuid4().hex
    
    # Get outcome service URL
    outcome_service_url = _get_outcome_service_url(request)
    
    # Build signed LTI parameters
    try:
        signed_params, launch_url = build_signed_lti_params(
            tool_name=tool,
            source_id=source_id,
            sub=sub,
            usr=usr,
            grp=grp,
            cid=cid,
            outcome_service_url=outcome_service_url,
            step_explanation=step_explanation,
            sid=sid,
            svc=svc
        )
    except ValueError as e:
        logger.error(f"[LTI Launch] ✗ Failed to build params: {e}")
        return HttpResponseBadRequest(str(e))
    
    # Cache launch context for outcome callback
    try:
        cache_entry = LTILaunchCache.get_or_create_cache(
            source_id=source_id,
            tool=tool,
            usr=usr,
            grp=grp,
            sub=sub,
            cid=cid,
            sid=sid,
            svc=svc,
            launch_url=launch_url,
            ttl_hours=LTI_CACHE_TTL_HOURS,
            module_id=module_id
        )
        logger.info(f"[LTI Launch] Cache stored: {source_id} (expires in {LTI_CACHE_TTL_HOURS}h)")
    except Exception as e:
        logger.error(f"[LTI Launch] ✗ Failed to cache launch context: {e}")
        return HttpResponseBadRequest('Unable to save the launch context. Please retry.')
    
    logger.info(
        f"[LTI Launch] ✓ Launching: tool={tool}, sub={sub}, "
        f"user={usr}, grp={grp}, module_id={module_id}"
    )
    logger.info(f"[LTI Launch] Target URL: {launch_url}")
    logger.info(f"[LTI Launch] Outcome URL: {outcome_service_url}")
    
    # Check if this is a PAWS proxy tool
    tool_config = get_tool_config(tool)
    is_paws_proxy = tool_config.get('is_paws_proxy', False) if tool_config else False

    if tool == 'paws_dbqa':
        # Keep DBQA's result and interaction APIs in the local tracking path.
        # PAWS signs the launch; its remote outcome alone cannot update a
        # localhost ModuLearn instance.
        from modulearn.views_proxy import _to_path_style
        return redirect(_to_path_style(launch_url))
    
    # Check for mixed content issues (HTTP tool in HTTPS context)
    parsed = urlparse(launch_url)
    if parsed.scheme == 'http' and request.is_secure():
        if is_paws_proxy:
            # For PAWS proxy, we need to proxy the HTTP content
            logger.info(f"[LTI Launch] PAWS tool is HTTP - routing through proxy")
            from django.urls import reverse
            proxy_path = launch_url.replace('http://', '/proxy/http/')
            response = redirect(proxy_path)
        else:
            logger.warning(
                f"[LTI Launch] ⚠ Mixed content: HTTP tool ({parsed.netloc}) "
                "from HTTPS context - may be blocked by browser"
            )
            # Continue with form-based launch, but browser may block
            context = {
                'action': launch_url,
                'params': signed_params,
            }
            response = render(request, 'lti/auto_submit.html', context)
    elif is_paws_proxy:
        # PAWS proxy tools: Use GET redirect with query params
        # The launch_url from build_paws_launch_params already has all query params
        # PAWS LTI consumer expects GET requests with query parameters
        logger.info(f"[LTI Launch] PAWS proxy tool - redirecting to PAWS with query params")
        logger.info(f"[LTI Launch] PAWS launch URL: {launch_url}")
        # For HTTP PAWS tools in HTTPS context, we need to proxy
        if parsed.scheme == 'http' and request.is_secure():
            # Proxy the HTTP URL using the path-style proxy
            from modulearn.views_proxy import _to_path_style
            proxy_url = _to_path_style(launch_url)
            response = redirect(proxy_url)
        else:
            # Direct redirect for HTTPS or same-scheme
            response = redirect(launch_url)
    else:
        # Direct LTI tools use form POST with OAuth-signed params
        if tool == 'dbqa':
            from modulearn.views_proxy import _to_path_style
            launch_url = _to_path_style(launch_url)
        context = {
            'action': launch_url,
            'params': signed_params,
        }
        response = render(request, 'lti/auto_submit.html', context)
        # OpenDSA identifies the consumer from Referer. Send only our origin,
        # never launch query parameters, when submitting its signed form.
        if tool in {'opendsa_problems', 'opendsa_slideshows'}:
            response['Referrer-Policy'] = 'origin'
    
    # Set headers to allow iframe embedding
    if 'X-Frame-Options' in response:
        del response['X-Frame-Options']
    response['Content-Security-Policy'] = "frame-ancestors 'self'"
    
    logger.info("=" * 60)
    return response


@csrf_exempt
@require_http_methods(["POST"])
@transaction.atomic
def outcome(request):
    """
    LTI Outcome Service endpoint.
    
    Receives LTI Outcome Service XML requests from tools when students
    complete activities. The score is extracted, validated, and:
    1. Forwarded to the User Modeling service (ADAPT2 protocol)
    2. Used to update local ModuleProgress records
    
    Request:
        POST with application/xml body containing LTI POX replaceResult request
        
    Returns:
        XML response (success or failure)
    """
    logger.info("=" * 60)
    logger.info("[LTI Outcome] Request received")
    logger.debug(f"[LTI Outcome] Content-Type: {request.content_type}")
    logger.debug(f"[LTI Outcome] Body length: {len(request.body)} bytes")
    
    # Initialize outcome log entry
    log_entry = LTIOutcomeLog(source_id='', tool='', score_raw='')
    
    try:
        # Parse the XML request
        try:
            source_id, score = parse_outcome_xml(request.body)
            logger.info(f"[LTI Outcome] Parsed: source_id={source_id}, score={score}")
        except ValueError as e:
            logger.error(f"[LTI Outcome] ✗ XML parse error: {e}")
            log_entry.error_message = str(e)
            log_entry.save()
            return HttpResponse(
                create_outcome_response(False, f"XML parse error: {e}"),
                content_type='text/xml'
            )
        
        log_entry.source_id = source_id
        log_entry.score_raw = score
        
        # Validate score format (should be 0.0-1.0)
        try:
            import math
            score_float = float(score)
            if not math.isfinite(score_float) or not 0 <= score_float <= 1:
                raise ValueError('Score must be finite and between zero and one.')
            log_entry.score_normalized = score_float
        except (ValueError, TypeError):
            log_entry.error_message = 'Invalid outcome score'
            log_entry.save()
            return HttpResponse(create_outcome_response(False, log_entry.error_message), content_type='text/xml', status=400)
        
        # Look up cached launch context
        cache_entry = LTILaunchCache.get_valid_cache(source_id)
        if not cache_entry:
            logger.warning(f"[LTI Outcome] ✗ Cache miss for source_id={source_id}")
            log_entry.error_message = "Launch context not found or expired"
            log_entry.save()
            return HttpResponse(
                create_outcome_response(False, "Launch context not found or expired"),
                content_type='text/xml'
            )
        
        log_entry.tool = cache_entry.tool
        cache_entry = LTILaunchCache.objects.select_for_update().get(pk=cache_entry.pk)

        from lti.outcome_auth import authenticate_outcome
        authenticated, duplicate = authenticate_outcome(request, get_tool_config(cache_entry.tool) or {})
        if not authenticated:
            log_entry.error_message = 'Invalid LTI outcome signature or body hash'
            log_entry.save()
            return HttpResponse(create_outcome_response(False, log_entry.error_message),
                                content_type='text/xml', status=401)
        if duplicate:
            return HttpResponse(create_outcome_response(True, 'Outcome already received'), content_type='text/xml')
        
        logger.info(
            f"[LTI Outcome] Cache hit: tool={cache_entry.tool}, "
            f"user_id={cache_entry.user_id}, module_id={cache_entry.module_id}, "
            f"instance_id={cache_entry.course_instance_id}"
        )
        
        # ============================================================
        # STEP 1: Update local ModuleProgress
        # ============================================================
        progress_updated = False
        if cache_entry.user_id and cache_entry.module_id:
            progress_updated = _update_module_progress(
                user_id=cache_entry.user_id,
                module_id=cache_entry.module_id,
                course_instance_id=cache_entry.course_instance_id,
                score=score_float,
                source_id=source_id
            )
        else:
            logger.warning(
                f"[LTI Outcome] ⚠ Cannot update progress: "
                f"user_id={cache_entry.user_id}, module_id={cache_entry.module_id}"
            )
        
        # ============================================================
        # STEP 2: Forward to UM Service (if enabled)
        # ============================================================
        um_success = False
        from courses.models import CourseInstance
        instructor_testing = CourseInstance.objects.filter(
            pk=cache_entry.course_instance_id, instructors__pk=cache_entry.user_id).exists()
        forward_to_um = LTI_FORWARD_TO_UM and not instructor_testing
        if forward_to_um:
            try:
                um_url = build_um_url(
                    base_um_url=UM_SERVICE_URL,
                    tool_name=cache_entry.tool,
                    source_id=source_id,
                    score=score,
                    usr=cache_entry.usr,
                    grp=cache_entry.grp,
                    sub=cache_entry.sub,
                    sid=cache_entry.sid,
                    svc=cache_entry.svc,
                    cid=cache_entry.cid
                )
                log_entry.um_url = um_url
                
                logger.info(f"[LTI Outcome] Forwarding to UM: {um_url}")
                
                um_response = requests.get(um_url, timeout=10)
                log_entry.um_response_status = um_response.status_code
                
                if um_response.status_code == 200:
                    logger.info(f"[LTI Outcome] ✓ UM service accepted score")
                    um_success = True
                else:
                    logger.error(f"[LTI Outcome] ✗ UM service returned {um_response.status_code}")
                    log_entry.error_message = f"UM service returned {um_response.status_code}"
                    
            except requests.Timeout:
                logger.error(f"[LTI Outcome] ✗ UM service timeout")
                log_entry.error_message = "UM service timeout"
            except requests.RequestException as e:
                logger.error(f"[LTI Outcome] ✗ UM service error: {e}")
                log_entry.error_message = str(e)
            except ValueError as e:
                logger.error(f"[LTI Outcome] ✗ Failed to build UM URL: {e}")
                log_entry.error_message = f"Failed to build UM URL: {e}"
        else:
            logger.info("[LTI Outcome] UM forwarding disabled (LTI_FORWARD_TO_UM=false)")
            um_success = True  # Don't fail if UM forwarding is disabled
        
        # ============================================================
        # Final Result
        # ============================================================
        # Success if either local progress was updated OR UM accepted the score
        overall_success = progress_updated or (forward_to_um and um_success)
        log_entry.success = overall_success
        log_entry.save()
        if overall_success:
            from lti.outcome_auth import remember_outcome
            remember_outcome(request)
        
        if overall_success:
            result_msg = f"Score {score} recorded"
            if progress_updated:
                result_msg += " (local progress updated)"
            if um_success and forward_to_um:
                result_msg += " (UM notified)"
            logger.info(f"[LTI Outcome] ✓ Success: {result_msg}")
        else:
            result_msg = "Failed to record score"
            logger.error(f"[LTI Outcome] ✗ {result_msg}")
        
        logger.info("=" * 60)
        return HttpResponse(
            create_outcome_response(overall_success, result_msg),
            content_type='text/xml'
        )
            
    except Exception as e:
        logger.exception(f"[LTI Outcome] ✗ Unexpected error: {e}")
        log_entry.error_message = f"Unexpected error: {e}"
        try:
            log_entry.save()
        except Exception:
            pass
        logger.info("=" * 60)
        return HttpResponse(
            create_outcome_response(False, "Internal server error"),
            content_type='text/xml'
        )


def health(request):
    """
    Health check endpoint for LTI service.
    
    Returns list of configured tools, cache statistics, and system status.
    """
    from django.utils import timezone
    
    configured = list_configured_tools()
    cache_count = LTILaunchCache.objects.filter(
        expires_at__gt=timezone.now()
    ).count()
    
    # Recent outcome statistics
    from datetime import timedelta
    recent_cutoff = timezone.now() - timedelta(hours=24)
    recent_outcomes = LTIOutcomeLog.objects.filter(received_at__gte=recent_cutoff)
    success_count = recent_outcomes.filter(success=True).count()
    failure_count = recent_outcomes.filter(success=False).count()
    
    response_data = {
        'status': 'ok',
        'configured_tools': configured,
        'active_cache_entries': cache_count,
        'um_forwarding_enabled': LTI_FORWARD_TO_UM,
        'um_service_url': UM_SERVICE_URL,
        'cache_ttl_hours': LTI_CACHE_TTL_HOURS,
        'outcomes_24h': {
            'success': success_count,
            'failure': failure_count,
            'total': success_count + failure_count,
        }
    }
    
    import json
    return HttpResponse(
        json.dumps(response_data, indent=2),
        content_type='application/json'
    )
