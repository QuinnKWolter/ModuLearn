import io
from urllib.parse import urlparse
import requests
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden

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

    print(f"DEBUG PROXY: Making request to: {src}")
    try:
        with requests.get(src, stream=True, timeout=8) as r:
            print(f"DEBUG PROXY: Response status: {r.status_code}")
            r.raise_for_status()
            ctype = r.headers.get("Content-Type", "application/octet-stream")
            print(f"DEBUG PROXY: Content type: {ctype}")
            total = 0
            buf = io.BytesIO()
            for chunk in r.iter_content(16384):
                if not chunk: continue
                total += len(chunk)
                if total > settings.PROXY_MAX_BYTES:
                    print(f"DEBUG PROXY: Content too large: {total} bytes")
                    return HttpResponseBadRequest("Too large")
                buf.write(chunk)
            print(f"DEBUG PROXY: Successfully fetched {total} bytes")
            resp = HttpResponse(buf.getvalue(), content_type=ctype)
            resp["Cache-Control"] = r.headers.get("Cache-Control", "public, max-age=3600")
            if getattr(settings, "PROXY_CORS_ORIGIN", None):
                resp["Access-Control-Allow-Origin"] = settings.PROXY_CORS_ORIGIN
            return resp
    except requests.RequestException as e:
        print(f"DEBUG PROXY: Request failed: {e}")
        return HttpResponseBadRequest("Upstream fetch failed")
