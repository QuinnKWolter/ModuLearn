import io
from urllib.parse import urlparse
import requests
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden

def http_get_proxy(request):
    if request.method not in ("GET", "HEAD"):
        return HttpResponseBadRequest("GET/HEAD only")
    src = request.GET.get("url")
    if not src:
        return HttpResponseBadRequest("Missing url")
    u = urlparse(src)
    if u.scheme != "http":
        return HttpResponseBadRequest("Only http:// allowed")
    if u.hostname not in settings.PROXY_ALLOWED_HOSTS:
        return HttpResponseForbidden("Host not allowed")

    try:
        with requests.get(src, stream=True, timeout=8) as r:
            r.raise_for_status()
            ctype = r.headers.get("Content-Type", "application/octet-stream")
            total = 0
            buf = io.BytesIO()
            for chunk in r.iter_content(16384):
                if not chunk: continue
                total += len(chunk)
                if total > settings.PROXY_MAX_BYTES:
                    return HttpResponseBadRequest("Too large")
                buf.write(chunk)
            resp = HttpResponse(buf.getvalue(), content_type=ctype)
            resp["Cache-Control"] = r.headers.get("Cache-Control", "public, max-age=3600")
            if getattr(settings, "PROXY_CORS_ORIGIN", None):
                resp["Access-Control-Allow-Origin"] = settings.PROXY_CORS_ORIGIN
            return resp
    except requests.RequestException:
        return HttpResponseBadRequest("Upstream fetch failed")
