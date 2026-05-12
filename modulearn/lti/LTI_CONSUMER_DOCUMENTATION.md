# LTI Tool Consumer Documentation

## Overview

ModuLearn includes an LTI 1.0/1.1 Tool Consumer that allows embedding external learning tools (CodeCheck, CTAT, CodeWorkout, etc.) within iframes and receiving score reports back from them.

**Key Features:**
- **Integrated with Course Structure**: Launches include `module_id` so outcomes update `ModuleProgress`
- **Dual Score Storage**: Updates both local database AND external UM service
- **Comprehensive Logging**: All operations logged with clear markers for debugging

**Important**: This is separate from the Canvas LTI Provider functionality (`lti/views.py`) which handles incoming launches FROM Canvas INTO ModuLearn.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              ModuLearn                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────┐  │
│  │ courses/     │    │ lti/         │    │ Database                 │  │
│  │ views.py     │───>│ views_lti.py │───>│ - ModuleProgress         │  │
│  │              │    │              │    │ - LTILaunchCache         │  │
│  │ Generates    │    │ Launch &     │    │ - LTIOutcomeLog          │  │
│  │ iframe_src   │    │ Outcome      │    │                          │  │
│  └──────────────┘    └──────┬───────┘    └──────────────────────────┘  │
└─────────────────────────────│───────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌──────────────────┐  ┌─────────────────┐
│   LTI Tool      │  │  LTI Tool        │  │  UM Service     │
│   (CodeCheck)   │  │  (CTAT, etc.)    │  │  (ADAPT2)       │
└─────────────────┘  └──────────────────┘  └─────────────────┘
```

## Data Flow

### Launch Flow
1. User clicks module in course → `courses/views.py:launch_iframe_module()`
2. Protocol detection → if LTI, generates URL: `/lti/tool-launch/?tool=X&sub=Y&usr=USER_ID&grp=INSTANCE_ID&module_id=MODULE_ID`
3. `views_lti.py:launch()` creates OAuth-signed request and caches context
4. Auto-submit form POSTs to tool provider
5. Tool renders in iframe

### Outcome Flow  
1. Student completes activity → Tool sends XML to `/lti/outcome/`
2. `views_lti.py:outcome()` parses XML, looks up cached context
3. **Local update**: Updates `ModuleProgress.score`, `progress`, `is_complete`
4. **UM forward**: Sends score to UM service via ADAPT2 protocol
5. Returns LTI POX success/failure response

## Endpoints

### `/lti/tool-launch/` (GET)

Launch an external LTI tool in an iframe.

**Query Parameters:**
| Parameter | Required | Description |
|-----------|----------|-------------|
| `tool` | Yes | Tool identifier (e.g., `codecheck`, `ctat`) |
| `sub` | Yes | Activity/resource identifier |
| `usr` | Yes | User identifier |
| `grp` | Yes | Group/context identifier |
| `cid` | No | Course ID |
| `sid` | No | Session ID |
| `svc` | No | Service identifier |
| `step_explanation` | No | DBQA-specific parameter |

**Example:**
```
/lti/tool-launch/?tool=codecheck&sub=activity123&usr=student1&grp=CS101
```

**Response:**
- HTML page with auto-submitting form that POSTs OAuth-signed LTI parameters to the tool provider
- Designed to be loaded in an iframe

### `/lti/outcome/` (POST)

Receive LTI Outcome Service callbacks from tools.

**Request:**
- Content-Type: `application/xml`
- Body: LTI POX `replaceResultRequest` XML

**Response:**
- LTI POX XML response (success or failure)

### `/lti/health/` (GET)

Health check endpoint showing configured tools and cache statistics.

## Configuration

### Environment Variables

Each tool requires three environment variables:

```bash
# CodeCheck
CODECHECK_KEY=your_consumer_key
CODECHECK_SECRET=your_consumer_secret
CODECHECK_LAUNCH=https://codecheck.io/lti

# CTAT
CTAT_KEY=your_key
CTAT_SECRET=your_secret
CTAT_LAUNCH=https://preview.ctat.cs.cmu.edu/run_lti_problem_set/...

# CodeWorkout
CODEWORKOUT_KEY=your_key
CODEWORKOUT_SECRET=your_secret
CODEWORKOUT_LAUNCH=https://codeworkout.cs.vt.edu/lti/launch

# CodeOcean
CODEOCEAN_KEY=your_key
CODEOCEAN_SECRET=your_secret
CODEOCEAN_LAUNCH=https://codeocean.openhpi.de/lti/launch

# CodeLab
CODELAB_KEY=your_key
CODELAB_SECRET=your_secret
CODELAB_LAUNCH=https://codelab.turingscraft.com/codelab/lti/launch

# DBQA
DBQA_KEY=your_key
DBQA_SECRET=your_secret
DBQA_LAUNCH=https://codesmell.org/dbqa/lti/1.1/launch

# OpenDSA Problems
OPENDSA_PROBLEMS_KEY=your_key
OPENDSA_PROBLEMS_SECRET=your_secret
OPENDSA_PROBLEMS_LAUNCH=https://opendsa-server.cs.vt.edu/lti/launch

# OpenDSA Slideshows
OPENDSA_SLIDESHOWS_KEY=your_key
OPENDSA_SLIDESHOWS_SECRET=your_secret
OPENDSA_SLIDESHOWS_LAUNCH=https://opendsa-server.cs.vt.edu/lti/launch
```

### Global Settings

```bash
# UM Service URL for score forwarding (ADAPT2 protocol)
UM_SERVICE_URL=http://adapt2.sis.pitt.edu/aggregate2/UserActivity

# Launch cache TTL in hours (default: 24)
LTI_CACHE_TTL_HOURS=24
```

### Adding a New Tool

1. Add tool configuration to `lti/config.py`:

```python
'newtool': {
    'consumer_key': os.getenv('NEWTOOL_KEY', ''),
    'consumer_secret': os.getenv('NEWTOOL_SECRET', ''),
    'launch_url': os.getenv('NEWTOOL_LAUNCH', 'https://newtool.example.com/lti'),
    'app_id': '99',  # For UM service
    'act': 'newtool',  # Activity type for UM service
    'lti_body_overrides': {
        # Optional: override default LTI parameters
        'custom_param': 'value',
    },
    # Optional: URL modifier function
    'launch_url_modifier': 'newtool_url_modifier',
    # Optional: score processor function
    'outcome_score_processor': 'newtool_score_processor',
},
```

2. If needed, add processor functions to `lti/config.py`:

```python
def newtool_url_modifier(base_url: str, sub: str) -> str:
    return f"{base_url}?activity={sub}"

def newtool_score_processor(score: str, sub: str) -> tuple:
    # Modify score or sub as needed
    return (score, sub)

# Add to PROCESSORS dict
PROCESSORS = {
    # ... existing processors ...
    'newtool_url_modifier': newtool_url_modifier,
    'newtool_score_processor': newtool_score_processor,
}
```

3. Set environment variables:
```bash
NEWTOOL_KEY=your_key
NEWTOOL_SECRET=your_secret
NEWTOOL_LAUNCH=https://newtool.example.com/lti
```

## Logging and Diagnostics

### Log Format

The LTI system uses structured logging with clear markers:

```
[LTI Launch] ✓ Launching: tool=codecheck, sub=activity1, user=10, grp=5, module_id=42
[LTI Launch] Target URL: https://codecheck.io/lti
[LTI Outcome] Parsed: source_id=10_5_activity1, score=0.85
[LTI Outcome] Cache hit: tool=codecheck, user_id=10, module_id=42, instance_id=5
[LTI→Progress] ✓ Updated: module=42 (Activity Name), user=10, score=0→85.0%
[LTI Outcome] ✓ Success: Score 0.85 recorded (local progress updated) (UM notified)
```

### Log Markers

| Marker | Meaning |
|--------|---------|
| `[LTI Launch]` | Tool launch processing |
| `[LTI Outcome]` | Outcome callback processing |
| `[LTI→Progress]` | Local ModuleProgress update |
| `[LTI Cache]` | Cache operations |
| `✓` | Success |
| `✗` | Error |
| `⚠` | Warning |

### Common Issues in Logs

**"Tool 'X' not configured"**
```
ERROR [LTI Launch] ✗ Tool 'codecheck' not configured. Configured tools: []
```
→ Set environment variables: `CODECHECK_KEY`, `CODECHECK_SECRET`, `CODECHECK_LAUNCH`

**"Cache miss for source_id"**
```
WARNING [LTI Outcome] ✗ Cache miss for source_id=user1_group1_activity1
```
→ Launch cache expired or server restarted. Increase `LTI_CACHE_TTL_HOURS` or check timing.

**"Cannot update progress: user_id=None, module_id=None"**
```
WARNING [LTI Outcome] ⚠ Cannot update progress: user_id=None, module_id=None
```
→ Launch URL missing `module_id` parameter. Check `courses/views.py` generates correct URL.

**"Mixed content warning"**
```
WARNING [LTI Launch] ⚠ Mixed content: HTTP tool (codecheck.io) from HTTPS context
```
→ Tool uses HTTP but ModuLearn is HTTPS. Browser may block iframe.

### Logging Configuration

In `settings.py`, adjust log levels as needed:

```python
'loggers': {
    'modulearn.views_lti': {
        'level': 'INFO',   # Change to 'DEBUG' for more detail
    },
    'lti': {
        'level': 'DEBUG',  # All LTI components
    },
}
```

### Admin Interface

View cached launches and outcome logs in Django Admin:
- `/admin/lti/ltilaunchcache/` - Active launch contexts
- `/admin/lti/ltioutcomelog/` - Outcome history with success/failure

### Health Check

Check system status at `/lti/health/`:
```json
{
  "status": "ok",
  "configured_tools": ["codecheck", "ctat"],
  "active_cache_entries": 15,
  "um_forwarding_enabled": true,
  "outcomes_24h": {
    "success": 42,
    "failure": 3,
    "total": 45
  }
}
```

---

## Production Deployment

### Reverse Proxy Headers

ModuLearn must correctly detect HTTPS when behind a reverse proxy. Ensure these settings in `settings.py`:

```python
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
```

Configure your reverse proxy (nginx) to forward headers:
```nginx
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header Host $host;
```

### Mixed Content (HTTP Tools in HTTPS)

If ModuLearn is served over HTTPS but a tool only supports HTTP:

1. **Best option**: Contact the tool provider to enable HTTPS
2. **Proxy option**: Use ModuLearn's HTTP proxy (`/proxy/`) for allowed hosts
3. **Warning**: Modern browsers block mixed active content

The `PROXY_ALLOWED_HOSTS` setting controls which HTTP hosts can be proxied:
```python
PROXY_ALLOWED_HOSTS = {
    "adapt2.sis.pitt.edu",
    "pawscomp2.sis.pitt.edu",
    # Add tool hosts as needed
}
```

### Iframe Headers

The launch view sets appropriate headers for iframe embedding:
- Removes `X-Frame-Options` header
- Sets `Content-Security-Policy: frame-ancestors 'self'`

If you need to allow framing from other domains, modify the view or use middleware.

### Cache Cleanup

The LTI launch cache stores context for outcome callbacks. Run periodic cleanup:

```bash
# Manual cleanup
python manage.py cleanup_lti_cache

# Dry run (show count without deleting)
python manage.py cleanup_lti_cache --dry-run

# Cron job (hourly)
0 * * * * cd /path/to/modulearn && python manage.py cleanup_lti_cache
```

## Security Considerations

### Input Validation

All query parameters (`tool`, `sub`, `usr`, `grp`) are validated:
- Must match `^[\w\-\.@]+$` pattern
- Maximum length enforced
- Special characters rejected

### XML Parsing

Uses `defusedxml` library to prevent:
- XML External Entity (XXE) attacks
- Entity expansion attacks
- Other XML-related vulnerabilities

### Secrets Management

- Tool credentials are loaded from environment variables
- Never committed to version control
- Use a secrets manager in production

### Outcome Endpoint

- CSRF exempt (tools don't have CSRF tokens)
- Validates `source_id` exists in cache
- Expired cache entries rejected
- All outcomes logged for auditing

## Troubleshooting

### "Tool not configured" Error

Check that environment variables are set:
```bash
echo $CODECHECK_KEY
echo $CODECHECK_SECRET
echo $CODECHECK_LAUNCH
```

### "Launch context not found" in Outcome

The cache entry may have expired. Check:
1. `LTI_CACHE_TTL_HOURS` setting
2. Time between launch and outcome callback
3. Server restarts (DB-backed cache survives restarts)

### OAuth Signature Failures

Tool providers may reject launches with invalid signatures. Check:
1. Consumer key and secret match the tool's configuration
2. Launch URL matches exactly (including trailing slashes)
3. System clock is accurate

### Mixed Content Warnings

If tools are blocked in HTTPS iframe:
1. Check browser console for mixed content errors
2. Verify tool supports HTTPS
3. Consider using the proxy for HTTP tools

## Database Models

### LTILaunchCache

Stores launch context for outcome callbacks:
- `source_id`: Unique identifier (format: `{usr}_{grp}_{sub}`)
- `tool`: Tool identifier
- `usr`, `grp`, `sub`, `cid`, `sid`, `svc`: Context parameters
- `expires_at`: Expiration timestamp

### LTIOutcomeLog

Audit log for outcome callbacks:
- `source_id`: Launch identifier
- `score_raw`: Raw score from tool
- `success`: Processing result
- `um_url`: URL called for UM service
- `error_message`: Error details if failed

## API Reference

### lti/services.py

| Function | Description |
|----------|-------------|
| `create_base_lti_body()` | Create base LTI parameters |
| `create_lti_body()` | Build tool-specific LTI body |
| `get_launch_url()` | Get launch URL with modifiers |
| `sign_lti_request()` | OAuth 1.0 signing |
| `build_signed_lti_params()` | Complete signed launch parameters |
| `build_um_url()` | Build UM service URL for outcomes |
| `parse_outcome_xml()` | Parse LTI outcome XML |
| `create_outcome_response()` | Generate POX XML response |
| `validate_identifier()` | Validate input parameters |
| `generate_source_id()` | Generate stable source_id |

### lti/config.py

| Function | Description |
|----------|-------------|
| `get_tool_configs()` | Get all tool configurations |
| `get_tool_config(name)` | Get config for specific tool |
| `is_tool_configured(name)` | Check if tool has credentials |
| `list_configured_tools()` | List tools with valid credentials |
| `get_processor(name)` | Get processor function by name |

