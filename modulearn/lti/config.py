"""
LTI Tool Consumer Configuration

This module provides a configuration-driven approach to LTI tool integration.
Instead of switch statements scattered across views, all tool-specific behavior
is defined here in a single, declarative structure.

To add a new tool:
1. Add entry to LTI_TOOL_CONFIGS with required fields
2. Set environment variables for key/secret/launch_url
3. (Optional) Add custom processors if tool has special behavior
"""
import os
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# TOOL-SPECIFIC PROCESSORS
# These are named functions referenced by tool configs for special behavior
# =============================================================================

def ctat_url_modifier(base_url: str, sub: str) -> str:
    """CTAT requires mg_{sub} appended to launch URL."""
    return f"{base_url.rstrip('/')}/mg_{sub}"


def ctat_score_processor(score: str, sub: str) -> tuple:
    """CTAT: any score > 0 becomes 1, else 0."""
    try:
        score_val = float(score)
        return ('1' if score_val > 0 else '0', sub)
    except (ValueError, TypeError):
        return ('0', sub)


def opendsa_url_modifier(base_url: str, sub: str) -> str:
    """OpenDSA requires custom_ex_settings and custom_ex_short_name in URL."""
    return f"{base_url}?custom_ex_settings=%7B%7D&custom_ex_short_name={sub}"


def dbqa_url_modifier(base_url: str, sub: str) -> str:
    """DBQA requires queryType parameter in URL."""
    return f"{base_url}?queryType={sub}"


def dbqa_score_processor(score: str, sub: str) -> tuple:
    """DBQA: append -lti to sub for UM service."""
    return (score, f"{sub}-lti")


def dbqa_act_modifier(act: str) -> str:
    """DBQA: append -lti to act for UM service."""
    return f"{act}-lti"


# Registry of processor functions (avoids lambdas in config for serializability)
PROCESSORS = {
    'ctat_url_modifier': ctat_url_modifier,
    'ctat_score_processor': ctat_score_processor,
    'opendsa_url_modifier': opendsa_url_modifier,
    'dbqa_url_modifier': dbqa_url_modifier,
    'dbqa_score_processor': dbqa_score_processor,
    'dbqa_act_modifier': dbqa_act_modifier,
}


def get_processor(name: str):
    """Get a processor function by name."""
    return PROCESSORS.get(name)


# =============================================================================
# TOOL CONFIGURATIONS
# =============================================================================

def get_tool_configs() -> dict:
    """
    Get tool configurations with credentials from environment.
    
    Each tool config supports:
    - consumer_key: OAuth consumer key (from env)
    - consumer_secret: OAuth consumer secret (from env)
    - launch_url: Base launch URL (from env)
    - app_id: Application ID for UM service
    - act: Activity type for UM service
    - lti_body_overrides: Dict of LTI param overrides (supports {usr}, {grp}, {sub}, etc.)
    - launch_url_modifier: Name of function to modify launch URL
    - outcome_score_processor: Name of function to process scores
    - outcome_act_modifier: Name of function to modify act for UM
    - is_paws_proxy: If True, this is a PAWS-mediated tool (no local OAuth signing)
    """
    return {
        # =====================================================================
        # PAWS-MEDIATED TOOLS
        # These tools are accessed via PAWS's LTI consumer at adapt2.sis.pitt.edu
        # PAWS handles OAuth signing - we just forward the request with params
        # =====================================================================
        'paws_codeocean': {
            'consumer_key': '',  # Not needed - PAWS handles auth
            'consumer_secret': '',
            'launch_url': os.getenv('PAWS_LTI_URL', 'http://adapt2.sis.pitt.edu/lti/launch'),
            'app_id': '54',
            'act': 'codeocean',
            'is_paws_proxy': True,
            'paws_tool': 'codeocean',  # Tool name to pass to PAWS
            # CodeOcean at openhpi.de has strict CSP - only allows their own domains
            'refuses_iframe': True,
            'refuses_iframe_reason': 'CodeOcean restricts embedding to *.openhpi.de domains only',
        },
        'paws_ctat': {
            'consumer_key': '',
            'consumer_secret': '',
            'launch_url': os.getenv('PAWS_LTI_URL', 'http://adapt2.sis.pitt.edu/lti/launch'),
            'app_id': '50',
            'act': 'ctat',
            'is_paws_proxy': True,
            'paws_tool': 'ctat',
        },
        'paws_codecheck': {
            'consumer_key': '',
            'consumer_secret': '',
            'launch_url': os.getenv('PAWS_LTI_URL', 'http://adapt2.sis.pitt.edu/lti/launch'),
            'app_id': '56',
            'act': 'codecheck',
            'is_paws_proxy': True,
            'paws_tool': 'codecheck',
        },
        # Note: PCEX is NOT an LTI tool - it's a standalone web app that reports
        # directly to PAWS's UM service. It cannot be routed through PAWS LTI.
        
        # =====================================================================
        # DIRECT TOOLS
        # These tools are called directly with our own credentials
        # =====================================================================
        'codecheck': {
            'consumer_key': os.getenv('CODECHECK_KEY', ''),
            'consumer_secret': os.getenv('CODECHECK_SECRET', ''),
            'launch_url': os.getenv('CODECHECK_LAUNCH', 'https://codecheck.io/lti'),
            'app_id': '56',
            'act': 'codecheck',
            'lti_body_overrides': {
                # CodeCheck uses defaults - no overrides needed
            },
        },
        
        'codeworkout': {
            'consumer_key': os.getenv('CODEWORKOUT_KEY', ''),
            'consumer_secret': os.getenv('CODEWORKOUT_SECRET', ''),
            'launch_url': os.getenv('CODEWORKOUT_LAUNCH', 'https://codeworkout.cs.vt.edu/lti/launch'),
            'app_id': '49',
            'act': 'codeworkout',
            'lti_body_overrides': {
                'lis_person_sourcedid': 'mastery_grids',
                'custom_course_name': 'Introduction to Java Programming',
                'custom_course_number': 'IS 0017',
                'custom_label': 'SPLICE',
                'custom_term': 'spring-2019',
            },
        },
        
        'ctat': {
            'consumer_key': os.getenv('CTAT_KEY', ''),
            'consumer_secret': os.getenv('CTAT_SECRET', ''),
            'launch_url': os.getenv('CTAT_LAUNCH', 'https://preview.ctat.cs.cmu.edu/run_lti_problem_set/ProgramCompFinal_ItgtModel_English'),
            'app_id': '50',
            'act': 'ctat',
            'lti_body_overrides': {
                'context_title': 'Python Mastery Grids Spring 2019',
                'context_label': 'Python Mastery Grids Spring 2019',
                'lis_person_sourcedid': '{usr}',  # Template: use user ID
            },
            'launch_url_modifier': 'ctat_url_modifier',
            'outcome_score_processor': 'ctat_score_processor',
        },
        
        'codelab': {
            'consumer_key': os.getenv('CODELAB_KEY', ''),
            'consumer_secret': os.getenv('CODELAB_SECRET', ''),
            'launch_url': os.getenv('CODELAB_LAUNCH', 'https://codelab.turingscraft.com/codelab/lti/launch'),
            'app_id': '52',
            'act': 'codelab',
            'lti_body_overrides': {
                'context_id': 'S3294476',  # Fixed context ID for CodeLab
                'context_title': 'Mastery Grids',
                'context_label': 'MasteryGrids',
                'lis_person_sourcedid': 'mastery_grids',
            },
        },
        
        'dbqa': {
            'consumer_key': os.getenv('DBQA_KEY', ''),
            'consumer_secret': os.getenv('DBQA_SECRET', ''),
            'launch_url': os.getenv('DBQA_LAUNCH', 'https://codesmell.org/dbqa/lti/1.1/launch'),
            'app_id': '53',
            'act': 'dbqa',
            'lti_body_overrides': {
                'resource_link_id': 'mg_{grp}_{sub}',
                'resource_link_title': 'mg_{grp}_{sub}',
                'resource_link_description': 'mg_{grp}_{sub}',
                'context_id': 'mg_{grp}',
                'context_title': 'Mastery Grids {grp}',
                'context_label': 'MasteryGrids {grp}',
                'lis_person_sourcedid': 'mastery_grids_{usr}',
            },
            'launch_url_modifier': 'dbqa_url_modifier',
            'outcome_score_processor': 'dbqa_score_processor',
            'outcome_act_modifier': 'dbqa_act_modifier',
        },
        
        'codeocean': {
            'consumer_key': os.getenv('CODEOCEAN_KEY', ''),
            'consumer_secret': os.getenv('CODEOCEAN_SECRET', ''),
            'launch_url': os.getenv('CODEOCEAN_LAUNCH', 'https://codeocean.openhpi.de/lti/launch'),
            'app_id': '54',
            'act': 'codeocean',
            'lti_body_overrides': {
                'custom_locale': 'en',
                'custom_course': 'splice-live-catalog',
                'custom_token': '{sub}',  # Activity identifier as token
                'lis_person_sourcedid': 'mastery_grids',
            },
        },
        
        'opendsa_problems': {
            'consumer_key': os.getenv('OPENDSA_PROBLEMS_KEY', ''),
            'consumer_secret': os.getenv('OPENDSA_PROBLEMS_SECRET', ''),
            'launch_url': os.getenv('OPENDSA_PROBLEMS_LAUNCH', 'https://opendsa-server.cs.vt.edu/lti/launch'),
            'app_id': '60',
            'act': 'opendsa_problems',
            'lti_body_overrides': {
                'custom_ex_short_name': '{sub}',
                'custom_ex_settings': '{}',
                'lis_person_sourcedid': 'mastery_grids',
            },
            'launch_url_modifier': 'opendsa_url_modifier',
        },
        
        'opendsa_slideshows': {
            'consumer_key': os.getenv('OPENDSA_SLIDESHOWS_KEY', ''),
            'consumer_secret': os.getenv('OPENDSA_SLIDESHOWS_SECRET', ''),
            'launch_url': os.getenv('OPENDSA_SLIDESHOWS_LAUNCH', 'https://opendsa-server.cs.vt.edu/lti/launch'),
            'app_id': '61',
            'act': 'opendsa_slideshows',
            'lti_body_overrides': {
                'custom_ex_short_name': '{sub}',
                'custom_ex_settings': '{}',
                'lis_person_sourcedid': 'mastery_grids',
            },
            'launch_url_modifier': 'opendsa_url_modifier',
        },
    }


def get_tool_config(tool_name: str) -> dict | None:
    """
    Get configuration for a specific tool.
    
    Args:
        tool_name: Tool identifier (e.g., 'codecheck')
        
    Returns:
        Tool configuration dict or None if tool not found
    """
    configs = get_tool_configs()
    return configs.get(tool_name)


def is_tool_configured(tool_name: str) -> bool:
    """
    Check if a tool has valid credentials configured.
    
    For PAWS proxy tools (is_paws_proxy=True), only launch_url is required
    since PAWS handles the actual OAuth signing.
    
    For direct tools, consumer_key, consumer_secret, and launch_url are required.
    
    Args:
        tool_name: Tool identifier
        
    Returns:
        True if tool is properly configured
    """
    config = get_tool_config(tool_name)
    if not config:
        return False
    
    # PAWS proxy tools only need a launch URL (PAWS handles OAuth)
    if config.get('is_paws_proxy'):
        return bool(config.get('launch_url'))
    
    # Direct tools need full credentials
    return bool(
        config.get('consumer_key') and 
        config.get('consumer_secret') and 
        config.get('launch_url')
    )


def list_configured_tools() -> list:
    """Return list of tools that have valid credentials."""
    return [name for name in get_tool_configs().keys() if is_tool_configured(name)]


def list_all_tools() -> list:
    """Return list of all defined tools (configured or not)."""
    return list(get_tool_configs().keys())

