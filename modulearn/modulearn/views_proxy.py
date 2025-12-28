import io, socket
from urllib.parse import urlparse
import requests
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, QueryDict
from django.views.decorators.csrf import csrf_exempt

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

def _rewrite_url(url: str, _base_url_ignored: str) -> str:
    """
    Input is expected to be ABSOLUTE already (we urljoin() in the caller).
    Convert http:// allowed-hosts to path-style; leave https/others unchanged.
    """
    if not url or url.startswith(('#', 'javascript:', 'mailto:')):
        return url

    # Handle protocol-relative absolute URLs
    if url.startswith('//'):
        url = f"http:{url}"

    # Now just convert absolute http URLs to path-style if allowed
    return _to_path_style(url)

@csrf_exempt
def http_get_proxy(request):
    print(f"DEBUG PROXY: Method: {request.method}")
    if request.method not in ("GET", "HEAD"):
        return HttpResponseBadRequest("GET/HEAD only")

    src = request.GET.get("url")
    print(f"DEBUG PROXY: URL param: {src}")
    if not src:
        return HttpResponseBadRequest("Missing url")

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
    if u.query:
        target += f"?{u.query}"
    headers = {"Host": u.hostname, "User-Agent": "ModuLearnProxy/1.0"}
    
    # Forward cookies from the original request to KnowledgeTree
    # This allows authenticated requests to KnowledgeTree to work through the proxy
    cookie_header = request.META.get("HTTP_COOKIE", "")
    if cookie_header:
        headers["Cookie"] = cookie_header

    print(f"DEBUG PROXY: Making request to (IPv4): {target} Host={u.hostname}")
    try:
        with requests.get(target, headers=headers, stream=True, timeout=8) as r:
            print(f"DEBUG PROXY: Response status: {r.status_code}")
            r.raise_for_status()
            ctype = r.headers.get("Content-Type", "application/octet-stream")
            print(f"DEBUG PROXY: Content type: {ctype}")
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
                original_length = len(content_str)
                
                # Base URL for rewriting: use the FULL page URL (directory-aware)
                import re
                from urllib.parse import urljoin
                base_for_join = f"{u.scheme}://{u.hostname}{u.path}"
                print(f"DEBUG PROXY: Base URL for rewriting (directory-aware): {base_for_join}")

                # Count rewrites
                rewrite_count = 0

                # Replace src, href, action (both " and ') with absolute resolution first
                def rewrite_match(m):
                    nonlocal rewrite_count
                    attr_name = m.group(1)
                    original_url = m.group(2)
                    # Resolve relative/absolute against the actual document URL (dir-aware)
                    resolved_abs = urljoin(base_for_join, original_url)
                    rewritten_url = _rewrite_url(resolved_abs, base_for_join)
                    if rewritten_url != original_url:
                        rewrite_count += 1
                        print(f"DEBUG PROXY: Rewrote {attr_name}: {original_url} -> {rewritten_url}")
                    return f'{attr_name}="{rewritten_url}"'

                content_str = re.sub(r'(src|href)="([^"]+)"', rewrite_match, content_str)
                content_str = re.sub(r"(src|href)='([^']+)'", rewrite_match, content_str)
                # Make action pattern consistent with src/href (include "action" as group 1)
                content_str = re.sub(r'(action)="([^"]+)"', rewrite_match, content_str)
                content_str = re.sub(r"(action)='([^']+)'", rewrite_match, content_str)
                
                content = content_str.encode('utf-8')
                print(f"DEBUG PROXY: Rewrote HTML content: {rewrite_count} URLs changed, {original_length} -> {len(content)} bytes")
            
            resp = HttpResponse(content, content_type=ctype)
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
    except requests.RequestException as e:
        print(f"DEBUG PROXY: Request failed: {e}")
        return HttpResponseBadRequest("Upstream fetch failed")

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

    # Reuse existing fetcher but bypass query-mode parsing
    # Create a new request-like object with the target URL
    class ProxyRequest:
        def __init__(self, original_request, target_url):
            self.method = original_request.method
            q = QueryDict(mutable=True)
            q["url"] = target_url
            self.GET = q
            self.META = original_request.META

    proxy_request = ProxyRequest(request, target)
    return http_get_proxy(proxy_request)