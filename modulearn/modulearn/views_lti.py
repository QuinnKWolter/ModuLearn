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
from urllib.parse import urlparse

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
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
        from courses.models import Module, ModuleProgress, Enrollment, CourseInstance
        from accounts.models import User
        
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
        
        # Find or create progress record
        if course_instance_id:
            try:
                course_instance = CourseInstance.objects.get(id=course_instance_id)
                progress, created = ModuleProgress.get_or_create_progress(
                    user=user, 
                    module=module, 
                    course_instance=course_instance
                )
            except CourseInstance.DoesNotExist:
                logger.warning(f"[LTI→Progress] CourseInstance {course_instance_id} not found for {source_id}")
                # Try without course instance
                progress = ModuleProgress.objects.filter(user=user, module=module).first()
                if not progress:
                    logger.warning(f"[LTI→Progress] No existing progress record for user={user_id}, module={module_id}")
                    return False
                created = False
        else:
            # No course instance (preview mode or external launch)
            progress = ModuleProgress.objects.filter(user=user, module=module).first()
            if not progress:
                logger.info(f"[LTI→Progress] No progress record for preview/external launch: {source_id}")
                return False
            created = False
        
        # Update progress
        old_score = progress.score
        old_progress = progress.progress
        
        # Only update if new score is better (or no score yet)
        if progress.score is None or score > progress.score:
            progress.score = score * 100  # Convert to percentage
            progress.progress = score
            progress.is_complete = score >= 1.0
            progress.success = score >= 0.7
            progress.attempts += 1
            progress.save()
            
            logger.info(
                f"[LTI→Progress] ✓ Updated: module={module_id} ({module.title}), "
                f"user={user_id}, score={old_score}→{progress.score:.1f}%, "
                f"progress={old_progress:.2f}→{progress.progress:.2f}, "
                f"complete={progress.is_complete}"
            )
            return True
        else:
            logger.info(
                f"[LTI→Progress] Skipped (score not better): module={module_id}, "
                f"user={user_id}, existing={progress.score:.1f}%, new={score*100:.1f}%"
            )
            return False
            
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
        sub = validate_identifier(request.GET.get('sub', ''), 'sub', max_length=512)
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
    
    # Generate source_id and cache launch context
    source_id = generate_source_id(usr, grp, sub)
    
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
        # Continue anyway - outcome forwarding will fail but launch should work
    
    logger.info(
        f"[LTI Launch] ✓ Launching: tool={tool}, sub={sub}, "
        f"user={usr}, grp={grp}, module_id={module_id}"
    )
    logger.info(f"[LTI Launch] Target URL: {launch_url}")
    logger.info(f"[LTI Launch] Outcome URL: {outcome_service_url}")
    
    # Check if this is a PAWS proxy tool
    tool_config = get_tool_config(tool)
    is_paws_proxy = tool_config.get('is_paws_proxy', False) if tool_config else False
    
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
        # PAWS proxy tools use GET redirect (PAWS handles the POST to the tool)
        logger.info(f"[LTI Launch] PAWS proxy tool - redirecting to PAWS")
        response = redirect(launch_url)
    else:
        # Direct LTI tools use form POST with OAuth-signed params
        context = {
            'action': launch_url,
            'params': signed_params,
        }
        response = render(request, 'lti/auto_submit.html', context)
    
    # Set headers to allow iframe embedding
    if 'X-Frame-Options' in response:
        del response['X-Frame-Options']
    response['Content-Security-Policy'] = "frame-ancestors 'self'"
    
    logger.info("=" * 60)
    return response


@csrf_exempt
@require_http_methods(["POST"])
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
            score_float = float(score)
            if score_float < 0:
                logger.warning(f"[LTI Outcome] Score clamped from {score_float} to 0.0")
                score_float = 0.0
            elif score_float > 1:
                logger.warning(f"[LTI Outcome] Score clamped from {score_float} to 1.0")
                score_float = 1.0
            log_entry.score_normalized = score_float
        except (ValueError, TypeError):
            logger.warning(f"[LTI Outcome] ⚠ Non-numeric score: '{score}'")
            score_float = 0.0
        
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
        if LTI_FORWARD_TO_UM:
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
        overall_success = progress_updated or um_success
        log_entry.success = overall_success
        log_entry.save()
        
        if overall_success:
            result_msg = f"Score {score} recorded"
            if progress_updated:
                result_msg += " (local progress updated)"
            if um_success and LTI_FORWARD_TO_UM:
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
