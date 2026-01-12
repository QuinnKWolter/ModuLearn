import io, socket
from urllib.parse import urlparse, urljoin
import requests
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, QueryDict, HttpResponseServerError, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
import logging
import re

logger = logging.getLogger(__name__)

def _resolve_ipv4(host: str, port: int = 80):
    # Return first IPv4 address or None
    infos = socket.getaddrinfo(host, port, family=socket.AF_INET, type=socket.SOCK_STREAM)
    return infos[0][4][0] if infos else None

def _to_path_style(url: str) -> str:
    """Convert URL to path-style proxy format if it's HTTP and allowed."""
    from urllib.parse import urlparse
    u = urlparse(url)
    if u.scheme == "http" and u.hostname in getattr(settings, "PROXY_ALLOWED_HOSTS", set()):
        path = u.path.lstrip('/')
        base = f"/proxy/http/{u.hostname}/{path}"
        proxied_url = f"{base}?{u.query}" if u.query else base
        
        # In production, Django may use FORCE_SCRIPT_NAME to prefix all URLs with /modulearn/
        # We need to include this prefix so the URL works correctly
        script_name = getattr(settings, 'FORCE_SCRIPT_NAME', '')
        if script_name:
            # Ensure script_name starts with / and doesn't end with /
            script_name = script_name.rstrip('/')
            if not script_name.startswith('/'):
                script_name = '/' + script_name
            proxied_url = script_name + proxied_url
        
        return proxied_url
    return url  # https or non-allowed hosts unchanged

def _is_login_page(content: str) -> bool:
    """
    Check if HTML content is a KnowledgeTree login page.
    
    Args:
        content: HTML content to check
    
    Returns:
        True if content appears to be a login page
    """
    if not content:
        return False
    
    content_lower = content.lower()
    
    # Check for login page indicators
    login_indicators = [
        'j_security_check',  # Login form action
        'j_username',        # Username input
        'j_password',        # Password input
        '/content/doauthenticate',  # Authentication servlet reference (case-insensitive)
    ]
    
    # Need at least 2 indicators to be confident it's a login page
    matches = sum(1 for indicator in login_indicators if indicator in content_lower)
    return matches >= 2


def _rewrite_url(url: str, _base_url_ignored: str) -> str:
    """
    Input is expected to be ABSOLUTE already (we urljoin() in the caller).
    Convert http:// allowed-hosts to path-style; leave https/others unchanged.
    
    CRITICAL: Never rewrite j_security_check URLs - they must go directly to KnowledgeTree.
    """
    if not url or url.startswith(('#', 'javascript:', 'mailto:')):
        return url

    # CRITICAL: Don't rewrite j_security_check URLs - they need direct access to KnowledgeTree
    if 'j_security_check' in url.lower():
        # Make it absolute if relative
        if url.startswith('/'):
            kt_config = getattr(settings, 'KNOWLEDGETREE', {})
            api_url = kt_config.get('API_URL', 'http://adapt2.sis.pitt.edu')
            return f"{api_url}{url}"
        # Already absolute - return as-is
        return url

    # Handle protocol-relative absolute URLs
    if url.startswith('//'):
        url = f"http:{url}"

    # Now just convert absolute http URLs to path-style if allowed
    return _to_path_style(url)

@csrf_exempt
def http_get_proxy(request, _redirect_depth=0):
    print(f"DEBUG PROXY REQUEST: Method={request.method}, Path={request.META.get('PATH_INFO', 'N/A')}, Query={request.META.get('QUERY_STRING', '')}, Depth={_redirect_depth}")
    
    # Safety check to prevent infinite loops
    if _redirect_depth > 10:
        print(f"ERROR PROXY: Redirect depth exceeded 10, possible infinite loop!")
        return HttpResponse("Too many redirects", status=508)
    
    # CRITICAL: Don't proxy j_security_check - it's container authentication that needs direct access
    path_info = request.META.get("PATH_INFO", "")
    if 'j_security_check' in path_info.lower():
        logger.warning(f"Attempted to proxy j_security_check - redirecting directly to KnowledgeTree")
        # Extract the path and redirect directly to KnowledgeTree
        script_name = getattr(settings, 'FORCE_SCRIPT_NAME', '')
        if script_name and path_info.startswith(script_name):
            path_info = path_info[len(script_name):]
        
        if path_info.startswith("/proxy/http/"):
            parts = path_info[len("/proxy/http/"):].split("/", 1)
            if len(parts) == 2:
                host, rest_path = parts
                kt_url = f"http://{host}/{rest_path}"
                # Add query string if present
                query_string = request.META.get('QUERY_STRING', '')
                if query_string:
                    kt_url += f"?{query_string}"
                logger.info(f"Redirecting j_security_check directly to KnowledgeTree: {kt_url}")
                return HttpResponseRedirect(kt_url)
    
    # Support GET, HEAD, and POST for form submissions
    if request.method not in ("GET", "HEAD", "POST"):
        return HttpResponseBadRequest("GET/HEAD/POST only")

    # For GET/HEAD, URL comes from query param; for POST, it comes from form action (rewritten to proxy URL)
    # We need to extract the original target URL from the request path
    if request.method in ("GET", "HEAD"):
        src = request.GET.get("url")
        print(f"DEBUG PROXY: URL param: {src}")
        if not src:
            return HttpResponseBadRequest("Missing url")
    else:
        # For POST, reconstruct URL from the proxy path
        # The path will be like /proxy/http/adapt2.sis.pitt.edu/kt/content/j_security_check
        path_info = request.META.get("PATH_INFO", "")
        # Remove script name prefix if present
        script_name = getattr(settings, 'FORCE_SCRIPT_NAME', '')
        if script_name and path_info.startswith(script_name):
            path_info = path_info[len(script_name):]
        
        # Extract from /proxy/http/<host>/<path>
        if path_info.startswith("/proxy/http/"):
            parts = path_info[len("/proxy/http/"):].split("/", 1)
            if len(parts) == 2:
                host, rest_path = parts
                src = f"http://{host}/{rest_path}"
            else:
                return HttpResponseBadRequest("Malformed proxy path for POST")
        else:
            return HttpResponseBadRequest("POST must use proxy path format")
        print(f"DEBUG PROXY: Reconstructed URL from path: {src}")

    u = urlparse(src)
    print(f"DEBUG PROXY: Parsed URL - scheme: {u.scheme}, hostname: {u.hostname}")
    if u.scheme != "http":
        return HttpResponseBadRequest("Only http:// allowed")

    print(f"DEBUG PROXY: Allowed hosts: {settings.PROXY_ALLOWED_HOSTS}")
    if u.hostname not in settings.PROXY_ALLOWED_HOSTS:
        print(f"DEBUG PROXY: Host {u.hostname} not in allowed hosts")
        return HttpResponseForbidden("Host not allowed")

    ip = _resolve_ipv4(u.hostname, 80)
    if not ip:
        return HttpResponseBadRequest("No IPv4 A record")

    # Build a URL targeting the IPv4 address but preserve Host for virtual hosting
    target = f"http://{ip}{u.path}"
    if u.query and request.method in ("GET", "HEAD"):
        target += f"?{u.query}"
    headers = {"Host": u.hostname, "User-Agent": "ModuLearnProxy/1.0"}
    
    # Forward cookies from the original request to KnowledgeTree
    # This allows authenticated requests to KnowledgeTree to work through the proxy
    cookie_header = request.META.get("HTTP_COOKIE", "")
    
    # Also add KnowledgeTree session cookies from Django session if available
    # Check if request has session attribute (real requests do, ProxyRequest might not)
    kt_session_cookies = {}
    if hasattr(request, 'session'):
        kt_session_cookies = request.session.get('kt_session_cookies', {})
    
    # Also check for JSESSIONID in request cookies (from browser)
    # Note: ProxyRequest/RedirectRequest objects don't have COOKIES attribute
    jsessionid_from_browser = None
    if hasattr(request, 'COOKIES'):
        jsessionid_from_browser = request.COOKIES.get('JSESSIONID')
    
    if kt_session_cookies:
        # Convert dict to cookie string format
        kt_cookies = '; '.join([f"{name}={value}" for name, value in kt_session_cookies.items()])
        if cookie_header:
            headers["Cookie"] = f"{cookie_header}; {kt_cookies}"
        else:
            headers["Cookie"] = kt_cookies
        print(f"DEBUG PROXY: Added {len(kt_session_cookies)} KT session cookies to request")
    elif jsessionid_from_browser:
        # Use JSESSIONID from browser cookies
        if cookie_header:
            headers["Cookie"] = cookie_header
        else:
            headers["Cookie"] = f"JSESSIONID={jsessionid_from_browser}"
        print(f"DEBUG PROXY: Using JSESSIONID from browser cookies")
    elif cookie_header:
        headers["Cookie"] = cookie_header
    
    # CRITICAL: For Show servlet requests, check if we have a session BEFORE making request
    # If not, return HTML with JavaScript that redirects top-level window (not iframe)
    # This prevents sandbox errors when redirecting from within an iframe
    url_param = request.GET.get("url", "") if request.method in ("GET", "HEAD") else ""
    query_string = request.META.get('QUERY_STRING', '')
    is_show_servlet = '/Show' in u.path and ('id=' in url_param or 'id=' in query_string)
    
    if is_show_servlet and hasattr(request, 'build_absolute_uri'):
        has_session = bool(
            jsessionid_from_browser or 
            (kt_session_cookies and kt_session_cookies.get('JSESSIONID'))
        )
        if not has_session:
            logger.warning(f"No KnowledgeTree session found for Show servlet request - will return login page if detected")
            # Don't redirect here - let the request go through to KnowledgeTree
            # If KnowledgeTree returns a login page, we'll detect it and return it in the iframe
            # The login form will POST directly to KnowledgeTree (not proxied), and after login,
            # KnowledgeTree will redirect. We handle that redirect server-side.

    print(f"DEBUG PROXY: Making {request.method} request to (IPv4): {target} Host={u.hostname}")
    try:
        # Handle POST requests with form data
        if request.method == "POST":
            # Get form data from request body
            data = request.POST.dict() if hasattr(request, 'POST') else {}
            # Also check for raw body data (for application/x-www-form-urlencoded)
            if not data and request.body:
                from urllib.parse import parse_qs
                data = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(request.body.decode('utf-8')).items()}
            
            print(f"DEBUG PROXY: POST data: {data}")
            # Use longer timeout for authentication endpoints (j_security_check)
            timeout = 30 if 'j_security_check' in target else 8
            with requests.post(target, headers=headers, data=data, stream=True, timeout=timeout, allow_redirects=False) as r:
                return _handle_proxy_response(r, u, request, follow_redirects=True, max_redirects=5, _redirect_depth=0)
        else:
            # GET or HEAD request
            with requests.get(target, headers=headers, stream=True, timeout=8, allow_redirects=False) as r:
                return _handle_proxy_response(r, u, request, follow_redirects=True, max_redirects=5, _redirect_depth=0)
    except requests.Timeout as e:
        print(f"DEBUG PROXY: Request timed out: {e}")
        return HttpResponse("Request timeout - the server took too long to respond", status=504)
    except requests.RequestException as e:
        print(f"DEBUG PROXY: Request failed: {e}")
        return HttpResponseBadRequest(f"Upstream fetch failed: {str(e)}")


def _handle_proxy_response(r, u, request, follow_redirects=True, max_redirects=5, _redirect_depth=0):
    """Handle proxy response, including redirects, content rewriting, and cookie forwarding.
    
    For iframe content, we follow redirects server-side instead of sending redirect responses
    to prevent top-level window navigation.
    """
    print(f"DEBUG PROXY RESPONSE: Status={r.status_code}, URL={u.geturl()}, FollowRedirects={follow_redirects}, MaxRedirects={max_redirects}, Depth={_redirect_depth}")
    
    # Prevent infinite redirect loops
    if _redirect_depth >= max_redirects:
        print(f"DEBUG PROXY REDIRECT: Max redirect depth reached ({_redirect_depth}), stopping to prevent loop")
        return HttpResponse("Too many redirects", status=508)
    
    # Handle redirects - for iframes, we follow them server-side instead of sending redirect
    if r.status_code in (301, 302, 303, 307, 308) and follow_redirects:
        location = r.headers.get("Location", "")
        print(f"DEBUG PROXY REDIRECT: Detected redirect {r.status_code}, Location header='{location}'")
        if location:
            # Resolve relative redirect URLs
            from urllib.parse import urljoin
            base_for_join = f"{u.scheme}://{u.hostname}{u.path}"
            resolved_abs = urljoin(base_for_join, location)
            
            # Check if redirect is to same host (KnowledgeTree internal redirect)
            redirect_parsed = urlparse(resolved_abs)
            print(f"DEBUG PROXY REDIRECT: Parsed redirect - hostname={redirect_parsed.hostname}, original_hostname={u.hostname}, resolved_abs={resolved_abs}")
            if redirect_parsed.hostname == u.hostname and redirect_parsed.hostname in getattr(settings, "PROXY_ALLOWED_HOSTS", set()):
                # Follow redirect server-side by making another proxy request
                print(f"DEBUG PROXY REDIRECT: SAME HOST - Following redirect server-side: {location} -> {resolved_abs}")
                
                # Build proxy path for the redirect target
                path = redirect_parsed.path.lstrip('/')
                script_name = getattr(settings, 'FORCE_SCRIPT_NAME', '')
                proxy_path = f"/proxy/http/{redirect_parsed.hostname}/{path}"
                if script_name:
                    proxy_path = script_name.rstrip('/') + proxy_path
                if redirect_parsed.query:
                    proxy_path += f"?{redirect_parsed.query}"
                
                # Create a new request to follow the redirect
                class RedirectRequest:
                    def __init__(self, original_request, proxy_path, redirect_depth):
                        self.method = "GET"  # Redirects are always GET
                        self.GET = QueryDict()
                        self.POST = QueryDict()
                        self.body = b''
                        self.META = original_request.META.copy()
                        self.META["PATH_INFO"] = proxy_path
                        self._redirect_depth = redirect_depth
                        # Preserve session from original request
                        if hasattr(original_request, 'session'):
                            self.session = original_request.session
                
                redirect_request = RedirectRequest(request, proxy_path, _redirect_depth + 1)
                print(f"DEBUG PROXY REDIRECT: Recursively calling http_get_proxy with proxy_path={proxy_path}, depth={_redirect_depth + 1}")
                # Recursively handle the redirect with increased depth counter
                return http_get_proxy(redirect_request, _redirect_depth=_redirect_depth + 1)
            else:
                # External redirect - for iframe content, we should follow ALL redirects server-side
                # Never send redirect responses to browser as they cause top-level navigation
                print(f"DEBUG PROXY REDIRECT: DIFFERENT HOST - Checking if allowed: {redirect_parsed.hostname}")
                if redirect_parsed.hostname in getattr(settings, "PROXY_ALLOWED_HOSTS", set()):
                    # It's an allowed host, follow it server-side (even if different host)
                    print(f"DEBUG PROXY REDIRECT: ALLOWED HOST - Following external redirect server-side: {location} -> {resolved_abs}")
                    path = redirect_parsed.path.lstrip('/')
                    script_name = getattr(settings, 'FORCE_SCRIPT_NAME', '')
                    proxy_path = f"/proxy/http/{redirect_parsed.hostname}/{path}"
                    if script_name:
                        proxy_path = script_name.rstrip('/') + proxy_path
                    if redirect_parsed.query:
                        proxy_path += f"?{redirect_parsed.query}"
                    
                    class RedirectRequest:
                        def __init__(self, original_request, proxy_path, redirect_depth):
                            self.method = "GET"
                            self.GET = QueryDict()
                            self.POST = QueryDict()
                            self.body = b''
                            self.META = original_request.META.copy()
                            self.META["PATH_INFO"] = proxy_path
                            self._redirect_depth = redirect_depth
                            # Preserve session from original request
                            if hasattr(original_request, 'session'):
                                self.session = original_request.session
                    
                    redirect_request = RedirectRequest(request, proxy_path, _redirect_depth + 1)
                    print(f"DEBUG PROXY REDIRECT: Recursively calling http_get_proxy for external redirect, proxy_path={proxy_path}, depth={_redirect_depth + 1}")
                    return http_get_proxy(redirect_request, _redirect_depth=_redirect_depth + 1)
                else:
                    # Not an allowed host - can't proxy, but still don't send redirect
                    # Instead, return an error or the redirect as HTML meta refresh
                    print(f"DEBUG PROXY REDIRECT: NOT ALLOWED HOST - Returning error page instead of redirect. Host: {redirect_parsed.hostname}, Location: {location}")
                    # Return error page instead of redirect
                    error_html = f"""
                    <!DOCTYPE html>
                    <html>
                    <head><title>Redirect Blocked</title></head>
                    <body>
                        <p>Cannot follow redirect to external host: {redirect_parsed.hostname}</p>
                        <p>Original redirect: <a href="{location}">{location}</a></p>
                    </body>
                    </html>
                    """
                    return HttpResponse(error_html, content_type="text/html", status=403)
    
    # For non-redirect responses, process content
    print(f"DEBUG PROXY RESPONSE: Not a redirect (status={r.status_code}), processing content")
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "application/octet-stream")
    print(f"DEBUG PROXY RESPONSE: Content type: {ctype}")
    total = 0
    buf = io.BytesIO()
    for chunk in r.iter_content(16384):
        if not chunk:
            continue
        total += len(chunk)
        if total > settings.PROXY_MAX_BYTES:
            print(f"DEBUG PROXY: Content too large: {total} bytes")
            return HttpResponseBadRequest("Too large")
        buf.write(chunk)
    print(f"DEBUG PROXY: Successfully fetched {total} bytes")
    
    # For HTML content, rewrite relative URLs to go through our proxy
    content = buf.getvalue()
    print(f"DEBUG PROXY: Content-Type: {ctype}")
    if ctype and ('text/html' in ctype.lower() or 'application/xhtml' in ctype.lower()):
        print("DEBUG PROXY: Detected HTML content, attempting URL rewriting")
        content_str = content.decode('utf-8', errors='ignore')
        
        # CRITICAL: Check if this is a login page - if so, return it as-is in the iframe
        # The login form will POST directly to KnowledgeTree (not proxied), and after login,
        # KnowledgeTree will redirect. We handle that redirect server-side.
        if _is_login_page(content_str):
            logger.warning(f"Detected KnowledgeTree login page in proxied content - returning login page for iframe")
            # Return the login page HTML as-is, but ensure form actions go directly to KnowledgeTree
            # The URL rewriting already handles this - j_security_check URLs are made absolute but not proxied
            # This allows the login form to work within the iframe
            logger.info(f"Returning login page HTML for iframe display")
            # Continue with normal URL rewriting (which will ensure j_security_check goes directly to KT)
        
        original_length = len(content_str)
        
        # Base URL for rewriting: use the FULL page URL (directory-aware)
        import re
        from urllib.parse import urljoin
        base_for_join = f"{u.scheme}://{u.hostname}{u.path}"
        print(f"DEBUG PROXY: Base URL for rewriting (directory-aware): {base_for_join}")

        # Count rewrites
        rewrite_count = 0

        # Replace src, href, action (both " and ') with absolute resolution first
        # CRITICAL: Don't rewrite j_security_check URLs
        def rewrite_match(m):
            nonlocal rewrite_count
            attr_name = m.group(1)
            original_url = m.group(2)
            
            # CRITICAL: Never rewrite j_security_check URLs - they must go directly to KnowledgeTree
            if 'j_security_check' in original_url.lower():
                # Make it absolute if relative, but don't proxy it
                if original_url.startswith('/'):
                    kt_config = getattr(settings, 'KNOWLEDGETREE', {})
                    api_url = kt_config.get('API_URL', 'http://adapt2.sis.pitt.edu')
                    absolute_url = f"{api_url}{original_url}"
                    logger.debug(f"Not proxying j_security_check, making absolute: {original_url} -> {absolute_url}")
                    return f'{attr_name}="{absolute_url}"'
                # Already absolute - return as-is
                return f'{attr_name}="{original_url}"'
            
            # Resolve relative/absolute against the actual document URL (dir-aware)
            resolved_abs = urljoin(base_for_join, original_url)
            rewritten_url = _rewrite_url(resolved_abs, base_for_join)
            if rewritten_url != original_url:
                rewrite_count += 1
                print(f"DEBUG PROXY: Rewrote {attr_name}: {original_url} -> {rewritten_url}")
            return f'{attr_name}="{rewritten_url}"'

        content_str = re.sub(r'(src|href)="([^"]+)"', rewrite_match, content_str)
        content_str = re.sub(r"(src|href)='([^']+)'", rewrite_match, content_str)
        
        # For form actions, use special handling to ensure j_security_check is not proxied
        def rewrite_action_match(m):
            nonlocal rewrite_count
            attr_name = m.group(1)
            original_url = m.group(2)
            
            # CRITICAL: Never rewrite j_security_check - make it absolute but don't proxy
            if 'j_security_check' in original_url.lower():
                if original_url.startswith('/'):
                    kt_config = getattr(settings, 'KNOWLEDGETREE', {})
                    api_url = kt_config.get('API_URL', 'http://adapt2.sis.pitt.edu')
                    absolute_url = f"{api_url}{original_url}"
                    logger.debug(f"Not proxying j_security_check form action, making absolute: {original_url} -> {absolute_url}")
                    return f'{attr_name}="{absolute_url}"'
                return f'{attr_name}="{original_url}"'
            
            # Resolve relative/absolute against the actual document URL (dir-aware)
            resolved_abs = urljoin(base_for_join, original_url)
            rewritten_url = _rewrite_url(resolved_abs, base_for_join)
            if rewritten_url != original_url:
                rewrite_count += 1
                print(f"DEBUG PROXY: Rewrote {attr_name}: {original_url} -> {rewritten_url}")
            return f'{attr_name}="{rewritten_url}"'
        
        content_str = re.sub(r'(action)="([^"]+)"', rewrite_action_match, content_str)
        content_str = re.sub(r"(action)='([^']+)'", rewrite_action_match, content_str)
        
        # Rewrite form targets that would navigate top-level window
        content_str = re.sub(r'<form([^>]*)\s+target=["\']_top["\']', r'<form\1 target="_self"', content_str, flags=re.IGNORECASE)
        content_str = re.sub(r'<form([^>]*)\s+target=["\']_parent["\']', r'<form\1 target="_self"', content_str, flags=re.IGNORECASE)
        
        # Rewrite links with target="_top" or target="_parent"
        content_str = re.sub(r'<a([^>]*)\s+target=["\']_top["\']', r'<a\1 target="_self"', content_str, flags=re.IGNORECASE)
        content_str = re.sub(r'<a([^>]*)\s+target=["\']_parent["\']', r'<a\1 target="_self"', content_str, flags=re.IGNORECASE)
        
        # DO NOT rewrite JavaScript - it causes infinite loops
        # DO NOT inject JavaScript blockers - they cause issues
        # The iframe sandbox will handle security
        
        content = content_str.encode('utf-8')
        print(f"DEBUG PROXY HTML: Rewrote {rewrite_count} URLs, {original_length} -> {len(content)} bytes")
    
    resp = HttpResponse(content, content_type=ctype, status=r.status_code)
    resp["Cache-Control"] = r.headers.get("Cache-Control", "public, max-age=3600")
    
    # Forward Set-Cookie headers from KnowledgeTree to the browser
    # This allows KnowledgeTree session cookies to be set for the proxy domain
    # Note: requests library's headers is a CaseInsensitiveDict (not Django's headers)
    # It doesn't have getlist(), so we use .get() which returns the header value
    # If there are multiple Set-Cookie headers, requests typically only exposes one
    # Domain restrictions may prevent some cookies from working, but this helps
    set_cookie_header = r.headers.get("Set-Cookie")
    if set_cookie_header:
        resp["Set-Cookie"] = set_cookie_header
    
    if getattr(settings, "PROXY_CORS_ORIGIN", None):
        resp["Access-Control-Allow-Origin"] = settings.PROXY_CORS_ORIGIN
    return resp

@csrf_exempt
def http_get_proxy_path(request, rest: str):
    """
    Accepts /proxy/<scheme>/<host>/<path...>?<query>
    Example: /proxy/http/pawscomp2.sis.pitt.edu/pcex/index.html?lang=PYTHON&set=py_bmi_calculator
    """
    print(f"DEBUG PATH PROXY: rest={rest}")
    
    # Split first two segments as scheme/host, rest is path
    parts = rest.split('/', 2)
    if len(parts) < 3:
        return HttpResponseBadRequest("Malformed proxy path")
    scheme, host, path_rest = parts[0], parts[1], parts[2]
    
    print(f"DEBUG PATH PROXY: scheme={scheme}, host={host}, path={path_rest}")
    
    if scheme != "http":
        return HttpResponseBadRequest("Only http scheme allowed")

    if host not in getattr(settings, "PROXY_ALLOWED_HOSTS", set()):
        return HttpResponseForbidden("Host not allowed")

    # Rebuild absolute target
    from urllib.parse import urlunparse
    query = request.META.get("QUERY_STRING", "")
    target = urlunparse((scheme, host, "/" + path_rest, "", query, ""))
    
    print(f"DEBUG PATH PROXY: target={target}")

    # For path-based proxy, handle POST differently from GET/HEAD
    try:
        if request.method == "POST":
            # For POST, we need to make http_get_proxy extract URL from PATH_INFO
            # Create a modified request with PATH_INFO set to the proxy path
            class ProxyRequest:
                def __init__(self, original_request, proxy_path):
                    self.method = original_request.method
                    self.GET = QueryDict()  # Empty for POST
                    self.POST = original_request.POST
                    self.body = original_request.body
                    # Set PATH_INFO to the proxy path so http_get_proxy can extract it
                    self.META = original_request.META.copy()
                    self.META["PATH_INFO"] = proxy_path
                    self._redirect_depth = getattr(original_request, '_redirect_depth', 0)
            
            # Reconstruct the proxy path (with script name if needed)
            script_name = getattr(settings, 'FORCE_SCRIPT_NAME', '')
            proxy_path = f"/proxy/http/{host}/{path_rest}"
            if script_name:
                proxy_path = script_name.rstrip('/') + proxy_path
            proxy_request = ProxyRequest(request, proxy_path)
            redirect_depth = getattr(request, '_redirect_depth', 0)
            result = http_get_proxy(proxy_request, _redirect_depth=redirect_depth)
            if result is None:
                return HttpResponseServerError("Proxy request returned None")
            return result
        else:
            # For GET/HEAD, use the query param approach
            class ProxyRequest:
                def __init__(self, original_request, target_url):
                    self.method = original_request.method
                    q = QueryDict(mutable=True)
                    q["url"] = target_url
                    self.GET = q
                    self.META = original_request.META
                    self._redirect_depth = getattr(original_request, '_redirect_depth', 0)
                    # Preserve session from original request
                    if hasattr(original_request, 'session'):
                        self.session = original_request.session

            proxy_request = ProxyRequest(request, target)
            redirect_depth = getattr(request, '_redirect_depth', 0)
            result = http_get_proxy(proxy_request, _redirect_depth=redirect_depth)
            if result is None:
                return HttpResponseServerError("Proxy request returned None")
            return result
    except Exception as e:
        print(f"ERROR PROXY PATH: Exception in http_get_proxy_path: {e}")
        import traceback
        traceback.print_exc()
        return HttpResponseServerError(f"Proxy error: {str(e)}")