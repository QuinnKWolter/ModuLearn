import io, socket
from http.cookies import SimpleCookie
from urllib.parse import urlparse, urljoin, parse_qs
import requests
from django.conf import settings
from django.http import FileResponse, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, QueryDict, HttpResponseServerError, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
import logging
import re
import json
from modulearn.learning.services.pcrs_tracking import PCRS_HOST, capture_pcrs_result_if_possible

logger = logging.getLogger(__name__)

PCRS_FEEDBACK_ASSETS = {
    "red-sad-face.jpg": "img/pcrs/red-sad-face.png",
    "yellow-happy-face.png": "img/pcrs/yellow-happy-face.png",
}


def pcrs_feedback_asset(request, filename: str):
    asset_path = PCRS_FEEDBACK_ASSETS.get(filename)
    if not asset_path:
        return HttpResponse(status=404)
    source_path = settings.BASE_DIR / "static" / asset_path
    if not source_path.is_file():
        return HttpResponse(status=404)
    content_type = "image/jpeg" if filename.endswith(".jpg") else "image/png"
    return FileResponse(source_path.open("rb"), content_type=content_type)


def _proxy_source_from_path(request) -> str | None:
    """Reconstruct an upstream URL from a path-style proxy request."""
    path_info = request.META.get("PATH_INFO", "")
    script_name = getattr(settings, "FORCE_SCRIPT_NAME", "") or ""
    if script_name and path_info.startswith(script_name):
        path_info = path_info[len(script_name):]

    proxy_match = re.match(r"^/proxy/(https?)/([^/]+)/(.*)$", path_info)
    if not proxy_match:
        return None

    scheme, host, rest_path = proxy_match.groups()
    if not host or not rest_path:
        return None

    source = f"{scheme}://{host}/{rest_path}"
    query_string = request.META.get("QUERY_STRING", "")
    if query_string and "?" not in source:
        source += f"?{query_string}"
    return source

def _resolve_ipv4(host: str, port: int = 80):
    # Return first IPv4 address or None
    infos = socket.getaddrinfo(host, port, family=socket.AF_INET, type=socket.SOCK_STREAM)
    return infos[0][4][0] if infos else None

def _to_path_style(url: str) -> str:
    """Convert URL to path-style proxy format if it is allowed."""
    from urllib.parse import urlparse
    u = urlparse(url)
    if u.scheme in {"http", "https"} and u.hostname in getattr(settings, "PROXY_ALLOWED_HOSTS", set()):
        path = u.path.lstrip('/')
        base = f"/proxy/{u.scheme}/{u.hostname}/{path}"
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
    return url

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


def _host_cookies(request, hostname: str) -> dict:
    if not hasattr(request, "session"):
        return {}
    jars = request.session.get("proxy_upstream_cookies", {})
    if not isinstance(jars, dict):
        return {}
    jar = jars.get(hostname, {})
    if not isinstance(jar, dict):
        return {}
    return {name: value for name, value in jar.items() if name and value}


def _host_cookie_header(request, hostname: str) -> str:
    return "; ".join(
        f"{name}={value}"
        for name, value in _host_cookies(request, hostname).items()
    )


def _set_cookie_headers(response) -> list[str]:
    raw_headers = getattr(getattr(response, "raw", None), "headers", None)
    if raw_headers is not None:
        get_all = getattr(raw_headers, "get_all", None)
        if callable(get_all):
            values = get_all("Set-Cookie") or []
            if values:
                return list(values)
    header = response.headers.get("Set-Cookie") if hasattr(response, "headers") else None
    return [header] if header else []


def _store_upstream_cookies(request, hostname: str, response):
    if not hasattr(request, "session") or not hostname:
        return
    headers = _set_cookie_headers(response)
    if not headers:
        return

    jars = request.session.get("proxy_upstream_cookies", {})
    if not isinstance(jars, dict):
        jars = {}
    jar = jars.get(hostname, {})
    if not isinstance(jar, dict):
        jar = {}

    changed = False
    for header in headers:
        cookie = SimpleCookie()
        try:
            cookie.load(header)
        except Exception:
            continue
        for name, morsel in cookie.items():
            jar[name] = morsel.value
            changed = True

    if changed:
        jars[hostname] = jar
        request.session["proxy_upstream_cookies"] = jars
        request.session.modified = True


def _proxied_referer_for_upstream(request, upstream_url) -> str:
    referer = request.META.get("HTTP_REFERER", "")
    if not referer:
        return ""
    parsed = urlparse(referer)
    prefix = f"/proxy/{upstream_url.scheme}/{upstream_url.hostname}/"
    path = parsed.path
    script_name = getattr(settings, "FORCE_SCRIPT_NAME", "") or ""
    if script_name and path.startswith(script_name.rstrip("/") + prefix):
        path = path[len(script_name.rstrip("/")):]
    if not path.startswith(prefix):
        return referer
    upstream_path = "/" + path[len(prefix):]
    rebuilt = f"{upstream_url.scheme}://{upstream_url.hostname}{upstream_path}"
    if parsed.query:
        rebuilt += f"?{parsed.query}"
    return rebuilt


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
    logger.debug(f"DEBUG PROXY REQUEST: Method={request.method}, Path={request.META.get('PATH_INFO', 'N/A')}, Query={request.META.get('QUERY_STRING', '')}, Depth={_redirect_depth}")
    
    # Safety check to prevent infinite loops
    if _redirect_depth > 10:
        logger.error(f"ERROR PROXY: Redirect depth exceeded 10, possible infinite loop!")
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

    # Query-style requests provide ?url=...; path-style requests encode the
    # scheme and host in PATH_INFO. Supporting both here also keeps internal
    # redirect requests from losing their destination.
    if request.method in ("GET", "HEAD"):
        src = request.GET.get("url") or _proxy_source_from_path(request)
        logger.debug(f"DEBUG PROXY: URL param: {src}")
        if not src:
            return HttpResponseBadRequest("Missing url")
    else:
        src = _proxy_source_from_path(request)
        if not src:
            return HttpResponseBadRequest("POST must use proxy path format")
        logger.debug(f"DEBUG PROXY: Reconstructed URL from path: {src}")

    u = urlparse(src)
    logger.debug(f"DEBUG PROXY: Parsed URL - scheme: {u.scheme}, hostname: {u.hostname}")
    if u.scheme not in {"http", "https"}:
        return HttpResponseBadRequest("Only http:// or https:// allowed")

    logger.debug(f"DEBUG PROXY: Allowed hosts: {settings.PROXY_ALLOWED_HOSTS}")
    if u.hostname not in settings.PROXY_ALLOWED_HOSTS:
        logger.debug(f"DEBUG PROXY: Host {u.hostname} not in allowed hosts")
        return HttpResponseForbidden("Host not allowed")

    if u.scheme == "http":
        ip = _resolve_ipv4(u.hostname, 80)
        if not ip:
            return HttpResponseBadRequest("No IPv4 A record")
        # Build a URL targeting the IPv4 address but preserve Host for virtual hosting
        target = f"http://{ip}{u.path}"
    else:
        # HTTPS must target the real hostname so TLS certificate validation works.
        target = f"https://{u.hostname}{u.path}"
    if u.query and request.method in ("GET", "HEAD", "POST"):
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
        logger.debug(f"DEBUG PROXY: Added {len(kt_session_cookies)} KT session cookies to request")
    elif jsessionid_from_browser:
        # Use JSESSIONID from browser cookies
        if cookie_header:
            headers["Cookie"] = cookie_header
        else:
            headers["Cookie"] = f"JSESSIONID={jsessionid_from_browser}"
        logger.debug(f"DEBUG PROXY: Using JSESSIONID from browser cookies")
    elif cookie_header:
        headers["Cookie"] = cookie_header
    host_cookies = _host_cookies(request, u.hostname)
    host_cookie_header = "; ".join(f"{name}={value}" for name, value in host_cookies.items())
    if u.hostname == PCRS_HOST:
        # PCRS uses Django session and CSRF cookies whose names collide with
        # ModuLearn's own cookies. Keep the upstream cookie namespace isolated.
        if host_cookie_header:
            headers["Cookie"] = host_cookie_header
        else:
            headers.pop("Cookie", None)
    elif host_cookie_header:
        headers["Cookie"] = f"{headers.get('Cookie')}; {host_cookie_header}" if headers.get("Cookie") else host_cookie_header
    for meta_name, header_name in {
        "HTTP_ACCEPT": "Accept",
        "HTTP_X_REQUESTED_WITH": "X-Requested-With",
        "HTTP_X_CSRFTOKEN": "X-CSRFToken",
    }.items():
        value = request.META.get(meta_name)
        if value:
            headers[header_name] = value
    if u.hostname == PCRS_HOST and host_cookies.get("csrftoken"):
        headers["X-CSRFToken"] = host_cookies["csrftoken"]
    if request.method == "POST":
        headers["Origin"] = f"{u.scheme}://{u.hostname}"
        upstream_referer = _proxied_referer_for_upstream(request, u)
        if upstream_referer:
            headers["Referer"] = upstream_referer
    
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

    logger.debug(f"DEBUG PROXY: Making {request.method} request to (IPv4): {target} Host={u.hostname}")
    try:
        # Handle POST requests
        if request.method == "POST":
            # Check Content-Type to determine how to forward the body
            content_type = request.META.get('CONTENT_TYPE', request.META.get('HTTP_CONTENT_TYPE', ''))
            
            # For JSON requests, forward the raw body
            if 'application/json' in content_type.lower():
                # Forward JSON body as-is
                json_data = request.body
                headers['Content-Type'] = 'application/json'
                logger.debug(f"DEBUG PROXY: POST JSON body (length: {len(json_data)} bytes)")
                timeout = 30 if 'j_security_check' in target else 8
                with requests.post(target, headers=headers, data=json_data, stream=True, timeout=timeout, allow_redirects=False) as r:
                    return _handle_proxy_response(r, u, request, follow_redirects=True, max_redirects=5, _redirect_depth=0)
            else:
                # For form data, parse as form-encoded
                data = request.POST.dict() if hasattr(request, 'POST') else {}
                # Also check for raw body data (for application/x-www-form-urlencoded)
                if not data and request.body:
                    from urllib.parse import parse_qs
                    data = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(request.body.decode('utf-8')).items()}
                if u.hostname == PCRS_HOST and host_cookies.get("csrftoken"):
                    data["csrftoken"] = host_cookies["csrftoken"]
                
                # Preserve Content-Type if present
                if content_type:
                    headers['Content-Type'] = content_type
                
                logger.debug(f"DEBUG PROXY: POST form data: {data}")
                # Use longer timeout for authentication endpoints (j_security_check)
                timeout = 30 if 'j_security_check' in target else 8
                with requests.post(target, headers=headers, data=data, stream=True, timeout=timeout, allow_redirects=False) as r:
                    return _handle_proxy_response(r, u, request, follow_redirects=True, max_redirects=5, _redirect_depth=0)
        else:
            # GET or HEAD request
            with requests.get(target, headers=headers, stream=True, timeout=8, allow_redirects=False) as r:
                return _handle_proxy_response(r, u, request, follow_redirects=True, max_redirects=5, _redirect_depth=0)
    except requests.Timeout as e:
        logger.warning(f"Proxy request timed out: {e}")
        return HttpResponse("Request timeout - the server took too long to respond", status=504)
    except requests.RequestException as e:
        logger.error(f"Proxy request failed: {e}")
        return HttpResponseBadRequest(f"Upstream fetch failed: {str(e)}")


def _handle_proxy_response(r, u, request, follow_redirects=True, max_redirects=5, _redirect_depth=0):
    """Handle proxy response, including redirects, content rewriting, and cookie forwarding.
    
    For iframe content, we follow redirects server-side instead of sending redirect responses
    to prevent top-level window navigation.
    """
    logger.debug(f"DEBUG PROXY RESPONSE: Status={r.status_code}, URL={u.geturl()}, FollowRedirects={follow_redirects}, MaxRedirects={max_redirects}, Depth={_redirect_depth}")
    _store_upstream_cookies(request, u.hostname, r)
    
    # Prevent infinite redirect loops
    if _redirect_depth >= max_redirects:
        logger.debug(f"DEBUG PROXY REDIRECT: Max redirect depth reached ({_redirect_depth}), stopping to prevent loop")
        return HttpResponse("Too many redirects", status=508)
    
    # Handle redirects - for iframes, we follow them server-side instead of sending redirect
    if r.status_code in (301, 302, 303, 307, 308) and follow_redirects:
        location = r.headers.get("Location", "")
        logger.debug(f"DEBUG PROXY REDIRECT: Detected redirect {r.status_code}, Location header='{location}'")
        if location:
            # Resolve relative redirect URLs
            from urllib.parse import urljoin
            base_for_join = f"{u.scheme}://{u.hostname}{u.path}"
            resolved_abs = urljoin(base_for_join, location)
            
            # Check if redirect is to same host (KnowledgeTree internal redirect)
            redirect_parsed = urlparse(resolved_abs)
            logger.debug(f"DEBUG PROXY REDIRECT: Parsed redirect - hostname={redirect_parsed.hostname}, original_hostname={u.hostname}, resolved_abs={resolved_abs}")
            if redirect_parsed.hostname == u.hostname and redirect_parsed.hostname in getattr(settings, "PROXY_ALLOWED_HOSTS", set()):
                # Follow redirect server-side by making another proxy request
                logger.debug(f"DEBUG PROXY REDIRECT: SAME HOST - Following redirect server-side: {location} -> {resolved_abs}")
                
                # Build proxy path for the redirect target
                path = redirect_parsed.path.lstrip('/')
                script_name = getattr(settings, 'FORCE_SCRIPT_NAME', '')
                redirect_scheme = redirect_parsed.scheme if redirect_parsed.scheme in {"http", "https"} else u.scheme
                proxy_path = f"/proxy/{redirect_scheme}/{redirect_parsed.hostname}/{path}"
                if script_name:
                    proxy_path = script_name.rstrip('/') + proxy_path
                if redirect_parsed.query:
                    proxy_path += f"?{redirect_parsed.query}"
                
                # Create a new request to follow the redirect
                class RedirectRequest:
                    def __init__(self, original_request, target_url, proxy_path, redirect_depth):
                        self.method = "GET"  # Redirects are always GET
                        self.GET = QueryDict(mutable=True)
                        self.GET["url"] = target_url
                        self.POST = QueryDict()
                        self.body = b''
                        self.META = original_request.META.copy()
                        self.META["PATH_INFO"] = proxy_path
                        self.META["QUERY_STRING"] = ""
                        self._redirect_depth = redirect_depth
                        # Preserve session from original request
                        if hasattr(original_request, 'session'):
                            self.session = original_request.session
                
                redirect_request = RedirectRequest(request, resolved_abs, proxy_path, _redirect_depth + 1)
                logger.debug(f"DEBUG PROXY REDIRECT: Recursively calling http_get_proxy with proxy_path={proxy_path}, depth={_redirect_depth + 1}")
                # Recursively handle the redirect with increased depth counter
                return http_get_proxy(redirect_request, _redirect_depth=_redirect_depth + 1)
            else:
                # External redirect - for iframe content, we should follow ALL redirects server-side
                # Never send redirect responses to browser as they cause top-level navigation
                logger.debug(f"DEBUG PROXY REDIRECT: DIFFERENT HOST - Checking if allowed: {redirect_parsed.hostname}")
                if redirect_parsed.hostname in getattr(settings, "PROXY_ALLOWED_HOSTS", set()):
                    # It's an allowed host, follow it server-side (even if different host)
                    logger.debug(f"DEBUG PROXY REDIRECT: ALLOWED HOST - Following external redirect server-side: {location} -> {resolved_abs}")
                    path = redirect_parsed.path.lstrip('/')
                    script_name = getattr(settings, 'FORCE_SCRIPT_NAME', '')
                    redirect_scheme = redirect_parsed.scheme if redirect_parsed.scheme in {"http", "https"} else u.scheme
                    proxy_path = f"/proxy/{redirect_scheme}/{redirect_parsed.hostname}/{path}"
                    if script_name:
                        proxy_path = script_name.rstrip('/') + proxy_path
                    if redirect_parsed.query:
                        proxy_path += f"?{redirect_parsed.query}"
                    
                    class RedirectRequest:
                        def __init__(self, original_request, target_url, proxy_path, redirect_depth):
                            self.method = "GET"
                            self.GET = QueryDict(mutable=True)
                            self.GET["url"] = target_url
                            self.POST = QueryDict()
                            self.body = b''
                            self.META = original_request.META.copy()
                            self.META["PATH_INFO"] = proxy_path
                            self.META["QUERY_STRING"] = ""
                            self._redirect_depth = redirect_depth
                            # Preserve session from original request
                            if hasattr(original_request, 'session'):
                                self.session = original_request.session
                    
                    redirect_request = RedirectRequest(request, resolved_abs, proxy_path, _redirect_depth + 1)
                    logger.debug(f"DEBUG PROXY REDIRECT: Recursively calling http_get_proxy for external redirect, proxy_path={proxy_path}, depth={_redirect_depth + 1}")
                    return http_get_proxy(redirect_request, _redirect_depth=_redirect_depth + 1)
                else:
                    # Not an allowed host - can't proxy, but still don't send redirect
                    # Instead, return an error or the redirect as HTML meta refresh
                    logger.debug(f"DEBUG PROXY REDIRECT: NOT ALLOWED HOST - Returning error page instead of redirect. Host: {redirect_parsed.hostname}, Location: {location}")
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
    logger.debug(f"DEBUG PROXY RESPONSE: Not a redirect (status={r.status_code}), processing content")
    ctype = r.headers.get("Content-Type", "application/octet-stream")
    logger.debug(f"DEBUG PROXY RESPONSE: Content type: {ctype}")
    total = 0
    buf = io.BytesIO()
    for chunk in r.iter_content(16384):
        if not chunk:
            continue
        total += len(chunk)
        if total > settings.PROXY_MAX_BYTES:
            logger.debug(f"DEBUG PROXY: Content too large: {total} bytes")
            return HttpResponseBadRequest("Too large")
        buf.write(chunk)
    logger.debug(f"DEBUG PROXY: Successfully fetched {total} bytes")
    
    # For HTML content, rewrite relative URLs to go through our proxy
    content = buf.getvalue()
    logger.debug(f"DEBUG PROXY: Content-Type: {ctype}")
    if ctype and ('text/html' in ctype.lower() or 'application/xhtml' in ctype.lower()):
        logger.debug("DEBUG PROXY: Detected HTML content, attempting URL rewriting")
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
        logger.debug(f"DEBUG PROXY: Base URL for rewriting (directory-aware): {base_for_join}")

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
                logger.debug(f"DEBUG PROXY: Rewrote {attr_name}: {original_url} -> {rewritten_url}")
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
                logger.debug(f"DEBUG PROXY: Rewrote {attr_name}: {original_url} -> {rewritten_url}")
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
        if _is_paws_activity_page(u):
            content_str = _inject_activity_api_rewrite_script(content_str)
        
        content = content_str.encode('utf-8')
        logger.debug(f"DEBUG PROXY HTML: Rewrote {rewrite_count} URLs, {original_length} -> {len(content)} bytes")
    elif _is_pcex_activity_data_response(u, ctype):
        _cache_pcex_activity_metadata(request, u, content)
    
    resp = HttpResponse(content, content_type=ctype, status=r.status_code)
    resp["Cache-Control"] = r.headers.get("Cache-Control", "public, max-age=3600")
    
    # Forward Set-Cookie headers from KnowledgeTree to the browser
    # This allows KnowledgeTree session cookies to be set for the proxy domain
    # Note: requests library's headers is a CaseInsensitiveDict (not Django's headers)
    # It doesn't have getlist(), so we use .get() which returns the header value
    # If there are multiple Set-Cookie headers, requests typically only exposes one
    # Domain restrictions may prevent some cookies from working, but this helps
    set_cookie_header = r.headers.get("Set-Cookie")
    if set_cookie_header and u.hostname != PCRS_HOST:
        resp["Set-Cookie"] = set_cookie_header
    
    if getattr(settings, "PROXY_CORS_ORIGIN", None):
        resp["Access-Control-Allow-Origin"] = settings.PROXY_CORS_ORIGIN
    return resp


def _is_paws_activity_page(parsed_url) -> bool:
    if (
        parsed_url.hostname in {"pawscomp2.sis.pitt.edu", "adapt2.sis.pitt.edu"}
        and (
            parsed_url.path.startswith("/pcex/")
            or parsed_url.path.startswith("/pcex-authoring/")
        )
    ):
        return True
    return parsed_url.hostname == PCRS_HOST and parsed_url.path.startswith("/mgrids/")


def _inject_activity_api_rewrite_script(content: str) -> str:
    script_name = getattr(settings, "FORCE_SCRIPT_NAME", "") or ""
    script_name = script_name.rstrip("/")
    pcrs_feedback_assets = {
        f"/mgrids/static/problems/img/{filename}": (
            f"{script_name}/mgrids/static/problems/img/{filename}"
        )
        for filename in PCRS_FEEDBACK_ASSETS
    }
    script = f"""
<script>
(function() {{
  const moduLearnPrefix = {json.dumps(script_name)};
  const pcrsFeedbackAssets = {json.dumps(pcrs_feedback_assets)};
  function localizeActivityUrl(url) {{
    if (typeof url !== 'string') return url;
    if (pcrsFeedbackAssets[url]) return pcrsFeedbackAssets[url];
    const absoluteMatch = url.match(/^https?:\\/\\/pawscomp2\\.sis\\.pitt\\.edu(\\/(?:pcex|cbum)\\/.*)$/i);
    if (absoluteMatch) return moduLearnPrefix + absoluteMatch[1];
    const adaptMatch = url.match(/^https?:\\/\\/adapt2\\.sis\\.pitt\\.edu(\\/(?:pcex|cbum)\\/.*)$/i);
    if (adaptMatch) return moduLearnPrefix + adaptMatch[1];
    const pcrsMatch = url.match(/^https?:\\/\\/pcrs\\.utm\\.utoronto\\.ca(\\/mgrids\\/.*)$/i);
    if (pcrsMatch) return moduLearnPrefix + '/proxy/https/pcrs.utm.utoronto.ca' + pcrsMatch[1];
    if (url.startsWith('/mgrids/')) return moduLearnPrefix + '/proxy/https/pcrs.utm.utoronto.ca' + url;
    if (url.startsWith('/pcex/') || url.startsWith('/cbum/')) return moduLearnPrefix + url;
    return url;
  }}

  const imageSrc = Object.getOwnPropertyDescriptor(window.HTMLImageElement.prototype, 'src');
  if (imageSrc && imageSrc.set) {{
    Object.defineProperty(window.HTMLImageElement.prototype, 'src', {{
      configurable: imageSrc.configurable,
      enumerable: imageSrc.enumerable,
      get: imageSrc.get,
      set: function(value) {{
        return imageSrc.set.call(this, localizeActivityUrl(value));
      }}
    }});
  }}

  const originalSetAttribute = window.Element.prototype.setAttribute;
  window.Element.prototype.setAttribute = function(name, value) {{
    if (this.tagName === 'IMG' && String(name).toLowerCase() === 'src') {{
      value = localizeActivityUrl(value);
    }}
    return originalSetAttribute.call(this, name, value);
  }};

  if (window.fetch) {{
    const originalFetch = window.fetch.bind(window);
    window.fetch = function(resource, init) {{
      if (typeof resource === 'string') {{
        resource = localizeActivityUrl(resource);
      }}
      return originalFetch(resource, init);
    }};
  }}

  if (window.XMLHttpRequest && window.XMLHttpRequest.prototype.open) {{
    const originalOpen = window.XMLHttpRequest.prototype.open;
    window.XMLHttpRequest.prototype.open = function(method, url) {{
      arguments[1] = localizeActivityUrl(url);
      return originalOpen.apply(this, arguments);
    }};
  }}

  if (navigator.sendBeacon) {{
    const originalSendBeacon = navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon = function(url, data) {{
      return originalSendBeacon(localizeActivityUrl(url), data);
    }};
  }}
}})();
</script>
"""
    if "moduLearnPrefix" in content:
        return content
    if re.search(r"</head\s*>", content, flags=re.IGNORECASE):
        return re.sub(r"</head\s*>", script + r"\g<0>", content, count=1, flags=re.IGNORECASE)
    return script + content


def _first_query_value(params: dict, key: str, default: str = "") -> str:
    value = params.get(key, default)
    if isinstance(value, list):
        return value[0] if value else default
    return value or default


def _referer_query_params(request) -> dict:
    referer = request.META.get("HTTP_REFERER", "")
    if not referer:
        return {}
    return parse_qs(urlparse(referer).query)


def _find_pcex_module(course, params: dict):
    from courses.models import Module

    module_id = _first_query_value(params, "module_id")
    if module_id:
        module = Module.objects.filter(id=module_id, unit__course=course).first()
        if module:
            return module

    set_id = _first_query_value(params, "set")
    challenge_id = _first_query_value(params, "ch")
    if not set_id and not challenge_id:
        return None

    for module in Module.objects.filter(unit__course=course).select_related("unit"):
        module_params = parse_qs(urlparse(module.content_url or "").query)
        if set_id and _first_query_value(module_params, "set") != set_id:
            continue
        if challenge_id and _first_query_value(module_params, "ch") != challenge_id:
            continue
        return module
    return None


def _is_pcex_activity_data_response(parsed_url, content_type: str) -> bool:
    return (
        parsed_url.hostname in {"pawscomp2.sis.pitt.edu", "adapt2.sis.pitt.edu"}
        and parsed_url.path.startswith("/pcex/")
        and "/data/" in parsed_url.path
        and parsed_url.path.endswith(".json")
        and "json" in (content_type or "").lower()
    )


def _pcex_context_key(params: dict) -> str:
    course_id = _first_query_value(params, "cid")
    username = _first_query_value(params, "usr")
    module_id = _first_query_value(params, "module_id")
    set_id = _first_query_value(params, "set")
    challenge_id = _first_query_value(params, "ch")
    return f"{course_id}:{username}:{module_id}:{set_id}:{challenge_id}"


def _session_pcex_state(request) -> dict:
    if not hasattr(request, "session"):
        return {}
    state = request.session.get("pcex_tracking_state")
    if not isinstance(state, dict):
        state = {}
        request.session["pcex_tracking_state"] = state
    return state


def _cache_pcex_activity_metadata(request, parsed_url, content: bytes):
    params = _referer_query_params(request)
    if not params:
        return
    context_key = _pcex_context_key(params)
    if not context_key.strip(":"):
        return

    try:
        payload = json.loads(content.decode("utf-8"))
    except (TypeError, ValueError, UnicodeDecodeError):
        logger.debug("[PCEX Tracking] Could not parse activity data JSON from %s", parsed_url.path)
        return

    goals = payload.get("activityGoals") if isinstance(payload, dict) else None
    if not isinstance(goals, list):
        return

    student_goal_count = sum(
        1 for goal in goals
        if isinstance(goal, dict) and not bool(goal.get("fullyWorkedOut"))
    )
    total_goal_count = student_goal_count or len(goals) or 1

    state = _session_pcex_state(request)
    existing = state.get(context_key, {})
    if not isinstance(existing, dict):
        existing = {}
    existing["goal_count"] = total_goal_count
    existing["activity_id"] = payload.get("activityName") or _first_query_value(params, "set")
    existing.setdefault("correct_tracking_ids", [])
    existing.setdefault("attempts", 0)
    state[context_key] = existing
    request.session["pcex_tracking_state"] = state
    request.session.modified = True
    logger.info("[PCEX Tracking] Cached %s student-facing goals for %s", total_goal_count, context_key)


def _pcex_result_state(request, params: dict, payload: dict) -> tuple[int, int, float, bool]:
    tracking_payload = _pcex_tracking_payload(payload)
    state = _session_pcex_state(request)
    context_key = _pcex_context_key(params)
    entry = state.get(context_key, {})
    if not isinstance(entry, dict):
        entry = {}

    try:
        goal_count = int(entry.get("goal_count") or 0)
    except (TypeError, ValueError):
        goal_count = 0
    if goal_count <= 0:
        goal_count = _infer_pcex_goal_count_from_remote(params) or 1
        entry["goal_count"] = goal_count
    goal_count = max(goal_count, 1)

    correct_ids = entry.get("correct_tracking_ids") or []
    if not isinstance(correct_ids, list):
        correct_ids = []

    correct = _pcex_payload_is_correct(tracking_payload)
    tracking_id = str(tracking_payload.get("tracking_id") or "").strip()
    if correct:
        if tracking_id and tracking_id not in correct_ids:
            correct_ids.append(tracking_id)
        elif not tracking_id:
            synthetic_id = f"correct-{len(correct_ids) + 1}"
            if synthetic_id not in correct_ids:
                correct_ids.append(synthetic_id)

    entry["correct_tracking_ids"] = correct_ids[:goal_count]
    entry["attempts"] = int(entry.get("attempts") or 0) + 1
    state[context_key] = entry
    if hasattr(request, "session"):
        request.session["pcex_tracking_state"] = state
        request.session.modified = True

    completed = min(len(entry["correct_tracking_ids"]), goal_count)
    progress = completed / goal_count
    return completed, goal_count, progress, correct


def _infer_pcex_goal_count_from_remote(params: dict) -> int | None:
    set_id = _first_query_value(params, "set")
    language = _first_query_value(params, "lang", "PYTHON") or "PYTHON"
    if not set_id:
        return None

    target_url = f"http://pawscomp2.sis.pitt.edu/pcex/pcex_v1/data/{language}_{set_id}.json"
    try:
        response = requests.get(target_url, timeout=4)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        logger.debug("[PCEX Tracking] Could not infer goal count from %s", target_url, exc_info=True)
        return None

    goals = payload.get("activityGoals") if isinstance(payload, dict) else None
    if not isinstance(goals, list):
        return None
    student_goal_count = sum(
        1 for goal in goals
        if isinstance(goal, dict) and not bool(goal.get("fullyWorkedOut"))
    )
    return student_goal_count or len(goals) or None


def _pcex_payload_is_correct(payload: dict) -> bool:
    return (
        str(payload.get("result", "")).lower() in {"1", "true"}
        or str(payload.get("result_type", "")).lower() == "correct"
    )


def _pcex_tracking_payload(payload: dict) -> dict:
    if isinstance(payload, dict) and isinstance(payload.get("trackingData"), dict):
        return payload["trackingData"]
    return payload if isinstance(payload, dict) else {}


def _capture_pcex_result_if_possible(request, rest: str, response: HttpResponse):
    if request.method != "POST" or rest.rstrip("/") != "api/track/result":
        return
    if getattr(response, "status_code", 500) >= 400:
        return

    try:
        payload = json.loads((request.body or b"{}").decode("utf-8"))
    except (TypeError, ValueError, UnicodeDecodeError):
        logger.warning("[PCEX Tracking] Could not parse result payload as JSON")
        return

    params = _referer_query_params(request)
    course_id = _first_query_value(params, "cid")
    username = _first_query_value(params, "usr")
    group_name = _first_query_value(params, "grp")
    if not (course_id and username):
        logger.warning("[PCEX Tracking] Missing cid/usr in referer; cannot map local progress")
        return

    try:
        from django.contrib.auth import get_user_model
        from courses.models import Course, CourseInstance, ModuleProgress
        from modulearn.learning.services.progress import apply_progress_snapshot

        course = Course.objects.filter(id=course_id).first()
        user = get_user_model().objects.filter(username=username).first()
        if not course or not user:
            logger.warning("[PCEX Tracking] Could not find course/user for cid=%s usr=%s", course_id, username)
            return

        instance_qs = CourseInstance.objects.filter(course=course, enrollments__student=user)
        if group_name:
            instance_qs = instance_qs.filter(group_name=group_name)
        course_instance = instance_qs.order_by("-active", "-id").first()
        module = _find_pcex_module(course, params)
        if not course_instance or not module:
            logger.warning(
                "[PCEX Tracking] Could not map course instance/module for cid=%s grp=%s module_id=%s",
                course_id,
                group_name,
                _first_query_value(params, "module_id"),
            )
            return

        completed, goal_count, progress, correct = _pcex_result_state(request, params, payload)
        score = progress * 100.0
        is_complete = progress >= 1.0

        module_progress, _ = ModuleProgress.get_or_create_progress(
            user=user,
            module=module,
            course_instance=course_instance,
        )
        progress = max(progress, module_progress.progress or 0.0)
        score = max(score, module_progress.score or 0.0)
        is_complete = bool(module_progress.is_complete or progress >= 1.0)
        apply_progress_snapshot(
            module_progress,
            source="pcex",
            progress=progress,
            score=score,
            success=correct,
            is_complete=is_complete,
            payload={
                "pcex_result": payload,
                "completed_goals": completed,
                "goal_count": goal_count,
                "progress_percent": score,
            },
            event_type="progress",
        )

        try:
            attempt_count = int(payload.get("attempt_count") or 0)
        except (TypeError, ValueError):
            attempt_count = 0
        if attempt_count and module_progress.attempts < attempt_count:
            module_progress.attempts = attempt_count
            module_progress.save(update_fields=["attempts", "last_accessed"])

        logger.info(
            "[PCEX Tracking] Recorded result for user=%s module=%s correct=%s progress=%s/%s",
            username,
            module.id,
            correct,
            completed,
            goal_count,
        )
    except Exception:
        logger.exception("[PCEX Tracking] Failed to record local progress")


@csrf_exempt
def forward_to_adapt2(request, rest: str):
    """
    Forward requests to pawscomp2.sis.pitt.edu for external activity API calls.
    
    Activities loaded in iframes make relative requests (e.g., /pcex/api/track/activity)
    that expect to be on pawscomp2.sis.pitt.edu. This endpoint catches those and forwards them.
    
    The route is `pcex/<path:rest>`, so `rest` is the path after `/pcex/`.
    We need to prepend `pcex/` when forwarding to pawscomp2.
    
    Example: /pcex/api/track/activity -> rest="api/track/activity" -> http://pawscomp2.sis.pitt.edu/pcex/api/track/activity
    
    POST requests with JSON bodies are forwarded with the original Content-Type and body.
    """
    target_host = 'pawscomp2.sis.pitt.edu'
    
    if target_host not in getattr(settings, 'PROXY_ALLOWED_HOSTS', set()):
        logger.warning(f"{target_host} not in PROXY_ALLOWED_HOSTS - cannot forward pcex requests")
        return HttpResponseForbidden(f"Proxy forwarding not configured for {target_host}")
    
    # Prepend 'pcex/' to the rest path since the route captures everything after /pcex/
    full_path = f"pcex/{rest}"
    
    logger.info(f"[PCEX Forward] Forwarding {request.method} /{full_path} -> {target_host}/{full_path}")
    
    # Build target URL
    query_string = request.META.get('QUERY_STRING', '')
    target_url = f"http://{target_host}/{full_path}"
    if query_string:
        target_url += f"?{query_string}"
    
    # For POST requests, we need to create a modified request with the proxy path in PATH_INFO
    if request.method == "POST":
        # Create a modified request that http_get_proxy can handle
        class ProxyRequest:
            def __init__(self, original_request, proxy_path):
                self.method = original_request.method
                self.GET = QueryDict()  # Empty for POST
                self.POST = original_request.POST
                self.body = original_request.body
                self.META = original_request.META.copy()
                self.META['PATH_INFO'] = proxy_path
                # Preserve Content-Type (important for JSON requests)
                if 'Content-Type' in original_request.META:
                    self.META['CONTENT_TYPE'] = original_request.META['Content-Type']
                elif 'HTTP_CONTENT_TYPE' in original_request.META:
                    self.META['CONTENT_TYPE'] = original_request.META['HTTP_CONTENT_TYPE']
                self._redirect_depth = getattr(original_request, '_redirect_depth', 0)
        
        script_name = getattr(settings, 'FORCE_SCRIPT_NAME', '')
        proxy_path = f"/proxy/http/{target_host}/{full_path}"
        if script_name:
            proxy_path = script_name.rstrip('/') + proxy_path
        
        proxy_request = ProxyRequest(request, proxy_path)
        response = http_get_proxy(proxy_request, _redirect_depth=0)
        _capture_pcex_result_if_possible(request, rest, response)
        return response
    else:
        # For GET/HEAD, use http_get_proxy_path which handles query params
        return http_get_proxy_path(request, f"http/{target_host}/{full_path}")


def forward_cbum(request, rest: str):
    """
    Forward requests to pawscomp2.sis.pitt.edu for CBUM (User Model) API calls.
    
    Activities loaded in iframes make relative requests (e.g., /cbum/um?app=46&act=...)
    that expect to be on pawscomp2.sis.pitt.edu. This endpoint catches those and forwards them.
    
    The route is `cbum/<path:rest>`, so `rest` is the path after `/cbum/`.
    We need to prepend `cbum/` when forwarding to pawscomp2.
    
    Example: /cbum/um?app=46&act=py_bmi_calculator1 -> rest="um" -> http://pawscomp2.sis.pitt.edu/cbum/um?app=46&act=py_bmi_calculator1
    """
    target_host = 'pawscomp2.sis.pitt.edu'
    
    if target_host not in getattr(settings, 'PROXY_ALLOWED_HOSTS', set()):
        logger.warning(f"{target_host} not in PROXY_ALLOWED_HOSTS - cannot forward cbum requests")
        return HttpResponseForbidden(f"Proxy forwarding not configured for {target_host}")
    
    # Prepend 'cbum/' to the rest path since the route captures everything after /cbum/
    full_path = f"cbum/{rest}"
    
    logger.info(f"[CBUM Forward] Forwarding {request.method} /{full_path} -> {target_host}/{full_path}")
    
    # Build target URL
    query_string = request.META.get('QUERY_STRING', '')
    target_url = f"http://{target_host}/{full_path}"
    if query_string:
        target_url += f"?{query_string}"
    
    # For POST requests, we need to create a modified request with the proxy path in PATH_INFO
    if request.method == "POST":
        # Create a modified request that http_get_proxy can handle
        class ProxyRequest:
            def __init__(self, original_request, proxy_path):
                self.method = original_request.method
                self.GET = QueryDict()  # Empty for POST
                self.POST = original_request.POST
                self.body = original_request.body
                self.META = original_request.META.copy()
                self.META['PATH_INFO'] = proxy_path
                # Preserve Content-Type (important for JSON requests)
                if 'Content-Type' in original_request.META:
                    self.META['CONTENT_TYPE'] = original_request.META['Content-Type']
                elif 'HTTP_CONTENT_TYPE' in original_request.META:
                    self.META['CONTENT_TYPE'] = original_request.META['HTTP_CONTENT_TYPE']
                self._redirect_depth = getattr(original_request, '_redirect_depth', 0)
        
        script_name = getattr(settings, 'FORCE_SCRIPT_NAME', '')
        proxy_path = f"/proxy/http/{target_host}/{full_path}"
        if script_name:
            proxy_path = script_name.rstrip('/') + proxy_path
        
        proxy_request = ProxyRequest(request, proxy_path)
        return http_get_proxy(proxy_request, _redirect_depth=0)
    else:
        # For GET/HEAD, use http_get_proxy_path which handles query params
        return http_get_proxy_path(request, f"http/{target_host}/{full_path}")

@csrf_exempt
def http_get_proxy_path(request, rest: str):
    """
    Accepts /proxy/<scheme>/<host>/<path...>?<query>
    Example: /proxy/http/pawscomp2.sis.pitt.edu/pcex/index.html?lang=PYTHON&set=py_bmi_calculator
    """
    logger.debug(f"DEBUG PATH PROXY: rest={rest}")
    
    # Split first two segments as scheme/host, rest is path
    parts = rest.split('/', 2)
    if len(parts) < 3:
        return HttpResponseBadRequest("Malformed proxy path")
    scheme, host, path_rest = parts[0], parts[1], parts[2]
    
    logger.debug(f"DEBUG PATH PROXY: scheme={scheme}, host={host}, path={path_rest}")
    
    if scheme not in {"http", "https"}:
        return HttpResponseBadRequest("Only http or https scheme allowed")

    if host not in getattr(settings, "PROXY_ALLOWED_HOSTS", set()):
        return HttpResponseForbidden("Host not allowed")

    # Rebuild absolute target
    from urllib.parse import urlunparse
    query = request.META.get("QUERY_STRING", "")
    target = urlunparse((scheme, host, "/" + path_rest, "", query, ""))
    
    logger.debug(f"DEBUG PATH PROXY: target={target}")

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
                    if hasattr(original_request, 'session'):
                        self.session = original_request.session
            
            # Reconstruct the proxy path (with script name if needed)
            script_name = getattr(settings, 'FORCE_SCRIPT_NAME', '')
            proxy_path = f"/proxy/{scheme}/{host}/{path_rest}"
            if script_name:
                proxy_path = script_name.rstrip('/') + proxy_path
            proxy_request = ProxyRequest(request, proxy_path)
            redirect_depth = getattr(request, '_redirect_depth', 0)
            result = http_get_proxy(proxy_request, _redirect_depth=redirect_depth)
            if result is None:
                return HttpResponseServerError("Proxy request returned None")
            if host in {"pawscomp2.sis.pitt.edu", "adapt2.sis.pitt.edu"} and path_rest.startswith("pcex/"):
                _capture_pcex_result_if_possible(request, path_rest[len("pcex/"):], result)
            capture_pcrs_result_if_possible(request, host, path_rest, result)
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
        logger.error(f"ERROR PROXY PATH: Exception in http_get_proxy_path: {e}")
        logger.exception("Exception in http_get_proxy_path")
        return HttpResponseServerError(f"Proxy error: {str(e)}")
