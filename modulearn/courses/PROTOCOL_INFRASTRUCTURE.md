# ModuLearn Protocol Infrastructure

## Overview

ModuLearn supports three protocols for loading smart-learning content in iframes:

| Protocol | Priority | Use Case | Communication |
|----------|----------|----------|---------------|
| **SPLICE** | 1 (Highest) | Modern tools (CodeCheck, etc.) | postMessage |
| **LTI** | 2 | LMS integration tools | OAuth-signed launch → postMessage |
| **PITT** | 3 (Lowest) | Legacy PAWS content | Direct HTTP (proxied) |

---

## Protocol Selection

**Location:** `courses/models.py` - `Module.select_launch_protocol()`

```python
def select_launch_protocol(self, preferred_order=None):
    if preferred_order is None:
        preferred_order = ['splice', 'lti', 'pitt']
    
    available = self.supported_protocols or []
    for protocol in preferred_order:
        if protocol in available:
            return protocol
    return None
```

Modules get their `supported_protocols` from the course-authoring API's `provider_protocols` map during course import (`courses/utils.py`).

---

## 1. SPLICE Protocol

### What It Is
SPLICE (Simple Protocol for Learning Integration and Content Exchange) uses `window.postMessage()` for parent-child iframe communication.

### Implementation

**JavaScript Handler:** `courses/templates/courses/module_frame.html`

1. **Probing**: Sends `SPLICE.getState`, `SPLICE.ping`, `SPLICE.hello` after iframe loads
2. **State Retrieval**: Responds to `SPLICE.getState` with stored `ModuleProgress.state_data`
3. **Progress Reporting**: Handles `SPLICE.reportScoreAndState` to update progress

**State Storage:** `ModuleProgress.state_data` (JSONField)

### URL Handling

For SPLICE protocol, the module's stored `content_url` is used directly:
- **HTTPS URLs**: Used as-is in the iframe
- **HTTP URLs** from `PROXY_ALLOWED_HOSTS`: Proxied through `/proxy/http/<host>/<path>`

No URL transformations are applied - the URL stored in the module database is the URL that's used.

### Allowed Origins
```javascript
// module_frame.html
const expectedOrigins = new Set([
  window.location.origin,      // ModuLearn (includes proxied content)
  'https://codecheck.me',     // CodeCheck
  'https://codecheck.io',     // CodeCheck alt
]);
```

---

## 2. LTI Protocol

### Two LTI Components (Different Purposes!)

| File | Purpose | Direction |
|------|---------|-----------|
| `lti/views.py` | Students launching INTO ModuLearn from Canvas | **Inbound** |
| `modulearn/views_lti.py` | ModuLearn embedding external LTI tools | **Outbound** |

**Do not consolidate** - they serve different purposes.

### Inbound LTI (Canvas → ModuLearn)

**Location:** `lti/views.py`

- Supports LTI 1.1 and 1.3
- Creates/updates users from Canvas
- Handles course enrollment
- Stores `lis_result_sourcedid` for grade passback

### Outbound LTI (ModuLearn → Tools)

**Location:** `modulearn/views_lti.py`

- OAuth 1.0 HMAC-SHA1 signing
- Renders auto-submit form → tool provider
- Caches launch context for outcomes

**Configuration:** `settings.py`
```python
LTI_TOOL_ENVS = {
    "codecheck": ("CODECHECK_KEY", "CODECHECK_SECRET", "CODECHECK_LAUNCH"),
    "codelab": ("CODELAB_KEY", "CODELAB_SECRET", "CODELAB_LAUNCH"),
    # ... etc
}
```

### iframe src Generation (LTI)

```python
# courses/views.py
if selected_protocol == 'lti':
    iframe_src = f"{reverse('lti_launch')}?tool={module.provider_id}&sub={lti_sub}&usr={user.id}&grp={instance.id}"
```

---

## 3. PITT Protocol (PAWS Content)

### What It Is
Legacy PAWS content from Pitt servers (columbus, pawscomp2, adapt2) served over HTTP.

### The Problem
ModuLearn is HTTPS; PAWS content is HTTP. Browsers block mixed content in iframes.

### The Solution: HTTP Proxy

**Location:** `modulearn/views_proxy.py`

**Features:**
- Path-style proxy: `/proxy/http/<host>/<path>`
- HTML URL rewriting (converts relative URLs to proxy URLs)
- Server-side redirect following (prevents top-level navigation)
- Cookie forwarding for KnowledgeTree authentication
- CORS headers

**Allowed Hosts:** `settings.py`
```python
PROXY_ALLOWED_HOSTS = {
    "columbus.exp.sis.pitt.edu",
    "pawscomp2.sis.pitt.edu",
    "adapt2.sis.pitt.edu",
    "localhost",
    "127.0.0.1",
}
```

### Proxy Decision Logic

```python
# courses/views.py
use_proxy = False
if content_url:
    parsed = urlparse(content_url)
    use_proxy = parsed.scheme == 'http' and parsed.hostname in PROXY_ALLOWED_HOSTS

if use_proxy:
    iframe_src = to_path_style_proxy(content_url)  # e.g., /proxy/http/pawscomp2.sis.pitt.edu/path
else:
    iframe_src = content_url
```

---

## Module Launch Flow

```
1. User clicks module → launch_iframe_module() or preview_iframe_module()
   
2. Parse content_url, extract query params (tool, sub)
   
3. If tool=codecheck with sub param → transform URL for SPLICE
   
4. Select protocol: Module.select_launch_protocol() → 'splice', 'lti', or 'pitt'
   
5. Determine if proxy needed (HTTP + allowed host)
   
6. Generate iframe_src:
   - LTI: /lti/launch/?tool=...&sub=...&usr=...&grp=...
   - Proxy: /proxy/http/<host>/<path>
   - Direct: content_url as-is (for HTTPS SPLICE content)
   
7. Render module_frame.html with iframe_src
   
8. JavaScript:
   - SPLICE: probe → state exchange → progress reporting
   - LTI: auto-submit form → tool loads → postMessage for events
   - PITT: direct render (proxied), no special JS
```

---

## Key Files

| File | Purpose |
|------|---------|
| `courses/models.py` | `Module.select_launch_protocol()`, `ModuleProgress.state_data` |
| `courses/views.py` | `launch_iframe_module()`, `preview_iframe_module()`, `to_path_style_proxy()` |
| `courses/templates/courses/module_frame.html` | SPLICE JavaScript, postMessage handlers |
| `modulearn/views_proxy.py` | HTTP proxy for PAWS content |
| `modulearn/views_lti.py` | Outbound LTI launches to external tools |
| `lti/views.py` | Inbound LTI launches from Canvas |
| `courses/utils.py` | `create_course_from_json()` - maps provider_protocols |

---

## Notes

1. **SPLICE is preferred** over LTI when both are available
2. **HTTP content is proxied** when hostname is in `PROXY_ALLOWED_HOSTS`
3. **HTTPS content loads directly** without proxy
4. **Proxied content** appears to come from `window.location.origin` for postMessage
5. **Canvas grade passback** uses `ModuleProgress` and `CourseProgress` LTI outcome methods
6. **State persistence** allows resuming exercises via `SPLICE.getState`

