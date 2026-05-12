"""
LTI Service Layer

This module provides core functionality for LTI 1.0/1.1 tool consumer operations:
- Building LTI launch request bodies
- OAuth 1.0 HMAC-SHA1 signing
- Building UM service URLs for outcome forwarding
- XML parsing utilities for outcome responses
"""
import re
import logging
from urllib.parse import urlencode, parse_qsl, urlparse
from typing import Optional
from oauthlib.oauth1 import Client
from defusedxml import ElementTree as ET

from .config import get_tool_config, get_processor

logger = logging.getLogger(__name__)


# =============================================================================
# LTI BODY BUILDING
# =============================================================================

def create_base_lti_body(source_id: str, usr: str, grp: str, 
                         sub: str, outcome_service_url: str) -> dict:
    """
    Create base LTI 1.0/1.1 body with all common fields.
    
    These fields are shared across all tools and follow the IMS LTI spec.
    Tool-specific overrides are applied on top of this base.
    
    Args:
        source_id: Unique identifier for this launch (for outcome callbacks)
        usr: User identifier
        grp: Group/context identifier
        sub: Activity/resource identifier
        outcome_service_url: URL for the LTI outcome service endpoint
        
    Returns:
        Dict of LTI parameters
    """
    return {
        # Required LTI parameters
        'lti_message_type': 'basic-lti-launch-request',
        'lti_version': 'LTI-1p0',
        
        # User identification
        'user_id': usr,
        'roles': 'Learner',  # Could be extended to support Instructor role
        'lis_person_name_full': usr,
        'lis_person_name_family': usr,
        'lis_person_name_given': usr,
        'lis_person_contact_email_primary': f'{usr}@mg.paws.edu',
        
        # Tool consumer (ModuLearn) identification
        'tool_consumer_info_product_family_code': 'modulearn',
        'tool_consumer_info_version': '1.1',
        'tool_consumer_instance_guid': 'modulearn.personalized-learning.org',
        'tool_consumer_instance_description': 'ModuLearn LMS',
        
        # Outcome service (for tools to report scores back)
        'lis_outcome_service_url': outcome_service_url,
        'lis_result_sourcedid': source_id,
        
        # Resource/link identification (templates - will be formatted)
        'resource_link_id': f'mg_{sub}',
        'resource_link_title': f'mg_{sub}',
        'resource_link_description': f'mg_{sub}',
        'ext_lti_assignment_id': f'modulearn_{sub}',
        
        # Context (course/group) identification
        'context_id': source_id,
        'context_title': source_id,
        'context_label': source_id,
        
        # Default person sourcedid
        'lis_person_sourcedid': 'modulearn',
        
        # Launch presentation
        'launch_presentation_document_target': 'iframe',
        
        # Extension for submit button text
        'ext_submit': 'Press to Launch',
    }


def create_lti_body(tool_name: str, source_id: str, sub: str, 
                    usr: str, grp: str, cid: str = '', 
                    outcome_service_url: str = '',
                    step_explanation: str = None) -> dict:
    """
    Create LTI body for a specific tool, applying config-driven overrides.
    
    This is the generalized builder that replaces all tool-specific
    create_*_lti_body() functions.
    
    Args:
        tool_name: Tool identifier (e.g., 'codecheck')
        source_id: Unique identifier for this launch
        sub: Activity/resource identifier
        usr: User identifier
        grp: Group/context identifier
        cid: Course ID (optional)
        outcome_service_url: URL for outcome service
        step_explanation: DBQA-specific parameter (optional)
        
    Returns:
        Dict of LTI parameters ready for OAuth signing
        
    Raises:
        ValueError: If tool is not configured
    """
    tool_config = get_tool_config(tool_name)
    if not tool_config:
        raise ValueError(f"Tool '{tool_name}' not found in configuration")
    
    # Create base body
    body = create_base_lti_body(source_id, usr, grp, sub, outcome_service_url)
    
    # Prepare template variables for string formatting
    format_vars = {
        'sub': sub,
        'grp': grp,
        'usr': usr,
        'cid': cid or '',
        'source_id': source_id,
    }
    
    # Apply tool-specific overrides from config
    overrides = tool_config.get('lti_body_overrides', {})
    for key, value in overrides.items():
        if isinstance(value, str) and '{' in value:
            # Template string - format it with our variables
            try:
                body[key] = value.format(**format_vars)
            except KeyError as e:
                logger.warning(f"Missing template variable {e} in override {key}")
                body[key] = value
        else:
            body[key] = value
    
    # Format any remaining template strings in base body
    for key, value in list(body.items()):
        if isinstance(value, str) and '{' in value:
            try:
                body[key] = value.format(**format_vars)
            except KeyError:
                pass  # Leave as-is if variable not found
    
    # Special handling for DBQA step_explanation
    if tool_name == 'dbqa' and step_explanation is not None:
        body['ext_display_step_explanation'] = step_explanation
    
    # Add course_id if provided
    if cid:
        body['course_id'] = cid
    
    return body


# =============================================================================
# LAUNCH URL HANDLING
# =============================================================================

def get_launch_url(tool_name: str, sub: str) -> str:
    """
    Get the launch URL for a tool, applying any URL modifiers.
    
    Args:
        tool_name: Tool identifier
        sub: Activity/resource identifier
        
    Returns:
        Final launch URL
        
    Raises:
        ValueError: If tool not configured
    """
    tool_config = get_tool_config(tool_name)
    if not tool_config:
        raise ValueError(f"Tool '{tool_name}' not found in configuration")
    
    launch_url = tool_config.get('launch_url', '')
    if not launch_url:
        raise ValueError(f"Tool '{tool_name}' has no launch_url configured")
    
    # Apply URL modifier if present
    modifier_name = tool_config.get('launch_url_modifier')
    if modifier_name:
        modifier = get_processor(modifier_name)
        if modifier:
            launch_url = modifier(launch_url, sub)
        else:
            logger.warning(f"URL modifier '{modifier_name}' not found for tool '{tool_name}'")
    
    return launch_url


# =============================================================================
# OAUTH SIGNING
# =============================================================================

def sign_lti_request(body: dict, consumer_key: str, consumer_secret: str, 
                     launch_url: str) -> dict:
    """
    Sign an LTI request using OAuth 1.0 HMAC-SHA1.
    
    Args:
        body: Dict of LTI parameters
        consumer_key: OAuth consumer key
        consumer_secret: OAuth consumer secret
        launch_url: Target URL for the LTI launch
        
    Returns:
        Dict of signed parameters (includes oauth_* params)
    """
    client = Client(
        consumer_key,
        client_secret=consumer_secret,
        signature_method='HMAC-SHA1',
        signature_type='BODY'
    )
    
    # Encode body for signing
    unsigned = urlencode(body)
    
    # Sign the request
    _, headers, signed_body = client.sign(
        launch_url,
        http_method='POST',
        body=unsigned,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )
    
    # Parse signed body back to dict
    signed_params = dict(parse_qsl(signed_body))
    
    return signed_params


def build_paws_launch_params(tool_name: str, source_id: str, sub: str,
                              usr: str, grp: str, cid: str = '',
                              sid: str = '', svc: str = '',
                              outcome_service_url: str = '') -> tuple[dict, str]:
    """
    Build launch parameters for PAWS-mediated tools.
    
    PAWS tools don't need our OAuth signing - we just build the URL with
    the right query parameters and let PAWS handle the actual LTI launch.
    
    Args:
        tool_name: PAWS tool identifier (e.g., 'paws_codeocean')
        source_id: Unique identifier for this launch
        sub: Activity/resource identifier
        usr: User identifier
        grp: Group/context identifier
        cid: Course ID (optional)
        sid: Session ID (optional)
        svc: Service ID (optional)
        outcome_service_url: URL for outcome service
        
    Returns:
        Tuple of (params dict for form, launch_url string with all params)
        
    Raises:
        ValueError: If tool not configured
    """
    tool_config = get_tool_config(tool_name)
    if not tool_config:
        raise ValueError(f"Tool '{tool_name}' not found in configuration")
    
    base_url = tool_config.get('launch_url', '')
    if not base_url:
        raise ValueError(f"Tool '{tool_name}' has no launch_url configured")
    
    # Get the actual tool name to pass to PAWS
    paws_tool = tool_config.get('paws_tool', tool_name.replace('paws_', ''))
    
    # Build query parameters for PAWS
    params = {
        'tool': paws_tool,
        'sub': sub,
        'usr': usr,
        'grp': grp,
    }
    
    # Add optional parameters if provided
    if cid:
        params['cid'] = cid
    if sid:
        params['sid'] = sid
    if svc:
        params['svc'] = svc
    
    # Include outcome service URL so PAWS can forward results
    if outcome_service_url:
        params['svc'] = outcome_service_url
    
    # Build full URL with query string
    launch_url = f"{base_url}?{urlencode(params)}"
    
    logger.info(f"[PAWS] Built launch URL: {launch_url}")
    
    return params, launch_url


def build_signed_lti_params(tool_name: str, source_id: str, sub: str,
                            usr: str, grp: str, cid: str = '',
                            outcome_service_url: str = '',
                            step_explanation: str = None,
                            sid: str = '', svc: str = '') -> tuple[dict, str]:
    """
    Build and sign LTI launch parameters for a tool.
    
    This is the main entry point for creating a signed LTI launch request.
    For PAWS proxy tools, delegates to build_paws_launch_params instead.
    
    Args:
        tool_name: Tool identifier
        source_id: Unique identifier for this launch
        sub: Activity/resource identifier
        usr: User identifier
        grp: Group/context identifier
        cid: Course ID (optional)
        outcome_service_url: URL for outcome service
        step_explanation: DBQA-specific parameter (optional)
        sid: Session ID (optional)
        svc: Service ID (optional)
        
    Returns:
        Tuple of (signed_params dict, launch_url string)
        
    Raises:
        ValueError: If tool not configured or missing credentials
    """
    tool_config = get_tool_config(tool_name)
    if not tool_config:
        raise ValueError(f"Tool '{tool_name}' not found in configuration")
    
    # Check if this is a PAWS proxy tool
    if tool_config.get('is_paws_proxy'):
        logger.info(f"[LTI] Using PAWS proxy for tool '{tool_name}'")
        return build_paws_launch_params(
            tool_name=tool_name,
            source_id=source_id,
            sub=sub,
            usr=usr,
            grp=grp,
            cid=cid,
            sid=sid,
            svc=svc,
            outcome_service_url=outcome_service_url
        )
    
    # Direct tool - do full OAuth signing
    consumer_key = tool_config.get('consumer_key', '')
    consumer_secret = tool_config.get('consumer_secret', '')
    
    if not consumer_key or not consumer_secret:
        raise ValueError(f"Tool '{tool_name}' missing credentials (set env vars)")
    
    # Build LTI body
    body = create_lti_body(
        tool_name=tool_name,
        source_id=source_id,
        sub=sub,
        usr=usr,
        grp=grp,
        cid=cid,
        outcome_service_url=outcome_service_url,
        step_explanation=step_explanation
    )
    
    # Get launch URL
    launch_url = get_launch_url(tool_name, sub)
    
    # Sign the request
    signed_params = sign_lti_request(body, consumer_key, consumer_secret, launch_url)
    
    return signed_params, launch_url


# =============================================================================
# UM SERVICE FORWARDING
# =============================================================================

def build_um_url(base_um_url: str, tool_name: str, source_id: str,
                 score: str, usr: str, grp: str, sub: str,
                 sid: str = '', svc: str = '', cid: str = '') -> str:
    """
    Build the User Modeling service URL for outcome forwarding.
    
    This converts LTI outcome results to ADAPT2 protocol for the UM service.
    
    Args:
        base_um_url: Base UM service URL
        tool_name: Tool identifier (to get app_id and act)
        source_id: Original launch source_id
        score: Score string from tool
        usr: User identifier
        grp: Group identifier
        sub: Activity identifier
        sid: Session ID
        svc: Service identifier
        cid: Course ID
        
    Returns:
        Complete UM service URL with all parameters
        
    Raises:
        ValueError: If tool not configured
    """
    tool_config = get_tool_config(tool_name)
    if not tool_config:
        raise ValueError(f"Tool '{tool_name}' not found in configuration")
    
    app_id = tool_config.get('app_id', '')
    act = tool_config.get('act', tool_name)
    
    # Apply score processor if present
    processor_name = tool_config.get('outcome_score_processor')
    if processor_name:
        processor = get_processor(processor_name)
        if processor:
            result = processor(score, sub)
            if isinstance(result, tuple):
                score, sub = result
            else:
                score = result
    
    # Apply act modifier if present
    act_modifier_name = tool_config.get('outcome_act_modifier')
    if act_modifier_name:
        act_modifier = get_processor(act_modifier_name)
        if act_modifier:
            act = act_modifier(act)
    
    # Build URL with all parameters
    params = {
        'app': app_id,
        'act': act,
        'sub': sub,
        'res': score,
        'usr': usr,
        'grp': grp,
        'sid': sid or '',
        'svc': svc or '',
        'cid': cid or '',
    }
    
    # Filter out empty values
    params = {k: v for k, v in params.items() if v}
    
    return f"{base_um_url}?{urlencode(params)}"


# =============================================================================
# XML PARSING (OUTCOME REQUESTS)
# =============================================================================

# LTI POX namespace
LTI_POX_NS = 'http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0'
LTI_POX_NSMAP = {'ims': LTI_POX_NS}


def parse_outcome_xml(xml_body: bytes) -> tuple[str, str]:
    """
    Parse LTI Outcome Service XML request.
    
    Uses defusedxml to prevent XXE attacks.
    
    Args:
        xml_body: Raw XML bytes from request
        
    Returns:
        Tuple of (source_id, score_string)
        
    Raises:
        ValueError: If XML is invalid or missing required fields
    """
    try:
        root = ET.fromstring(xml_body)
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML: {e}")
    
    # Find sourcedId (source_id)
    sourcedid_elem = root.find('.//{%s}sourcedId' % LTI_POX_NS)
    if sourcedid_elem is None:
        # Try without namespace (some tools don't use it)
        sourcedid_elem = root.find('.//sourcedId')
    
    if sourcedid_elem is None or not sourcedid_elem.text:
        raise ValueError("Missing sourcedId in outcome XML")
    
    source_id = sourcedid_elem.text.strip()
    
    # Find score (textString)
    score_elem = root.find('.//{%s}textString' % LTI_POX_NS)
    if score_elem is None:
        # Try without namespace
        score_elem = root.find('.//textString')
    
    if score_elem is None or score_elem.text is None:
        raise ValueError("Missing textString (score) in outcome XML")
    
    score = score_elem.text.strip()
    
    return source_id, score


def create_outcome_response(success: bool, description: str = '', 
                            message_ref_id: str = '') -> str:
    """
    Create LTI POX outcome response XML.
    
    Args:
        success: Whether the outcome processing succeeded
        description: Description message
        message_ref_id: Reference ID (usually timestamp)
        
    Returns:
        XML response string
    """
    import time
    import uuid
    
    if not message_ref_id:
        message_ref_id = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    code_major = 'success' if success else 'failure'
    severity = 'status' if success else 'error'
    
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<imsx_POXEnvelopeResponse xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
  <imsx_POXHeader>
    <imsx_POXResponseHeaderInfo>
      <imsx_version>V1.0</imsx_version>
      <imsx_messageIdentifier>{uuid.uuid4()}</imsx_messageIdentifier>
      <imsx_statusInfo>
        <imsx_codeMajor>{code_major}</imsx_codeMajor>
        <imsx_severity>{severity}</imsx_severity>
        <imsx_description>{description}</imsx_description>
        <imsx_messageRefIdentifier>{message_ref_id}</imsx_messageRefIdentifier>
      </imsx_statusInfo>
    </imsx_POXResponseHeaderInfo>
  </imsx_POXHeader>
  <imsx_POXBody>
    <replaceResultResponse/>
  </imsx_POXBody>
</imsx_POXEnvelopeResponse>"""
    
    return xml


# =============================================================================
# VALIDATION
# =============================================================================

# Allowed characters for LTI identifiers
SAFE_ID_PATTERN = re.compile(r'^[\w\-\.@]+$')


def validate_identifier(value: str, name: str, max_length: int = 255) -> str:
    """
    Validate an LTI identifier parameter.
    
    Args:
        value: The value to validate
        name: Parameter name (for error messages)
        max_length: Maximum allowed length
        
    Returns:
        The validated value (stripped)
        
    Raises:
        ValueError: If validation fails
    """
    if not value:
        raise ValueError(f"Missing required parameter: {name}")
    
    value = value.strip()
    
    if len(value) > max_length:
        raise ValueError(f"Parameter '{name}' exceeds maximum length ({max_length})")
    
    if not SAFE_ID_PATTERN.match(value):
        raise ValueError(f"Parameter '{name}' contains invalid characters")
    
    return value


def generate_source_id(usr: str, grp: str, sub: str) -> str:
    """
    Generate a stable, unique source_id from launch parameters.
    
    The source_id is used to correlate outcome callbacks with launches.
    Format: "{usr}_{grp}_{sub}"
    
    Args:
        usr: User identifier
        grp: Group identifier
        sub: Activity identifier
        
    Returns:
        Source ID string
    """
    return f"{usr}_{grp}_{sub}"

