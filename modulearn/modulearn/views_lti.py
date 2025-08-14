import os, uuid, time
from urllib.parse import urlencode, parse_qsl
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.core.cache import cache
from oauthlib.oauth1 import Client

REQUIRED_QUERY = ("tool", "sub", "usr", "grp")  # align with your callers

def _tool_env(tool: str):
    if tool not in settings.LTI_TOOL_ENVS:
        return None, None, None
    k_env, s_env, u_env = settings.LTI_TOOL_ENVS[tool]
    return os.getenv(k_env), os.getenv(s_env), os.getenv(u_env)

def _build_lti_body(tool, source_id, sub, usr, grp, cid=None, sid=None, svc=None, extra=None):
    # Minimal, extend per-tool as needed to match your Node lti_messager
    params = {
        "lti_message_type": "basic-lti-launch-request",
        "lti_version": "LTI-1p0",
        "resource_link_id": source_id,
        "user_id": usr or str(uuid.uuid4()),
        "roles": "Learner",
        "context_id": grp or "context",
        "launch_presentation_document_target": "iframe",
    }
    if cid: params["course_id"] = cid
    if sub: params["ext_ims_lis_resultvalue_sourcedidsub"] = sub  # example custom field
    if extra: params.update(extra)
    return params

def launch(request):
    for q in REQUIRED_QUERY:
        if q not in request.GET:
            return HttpResponseBadRequest(f"Missing '{q}'")
    tool = request.GET["tool"]
    sub  = request.GET["sub"]
    usr  = request.GET["usr"]
    grp  = request.GET["grp"]
    cid  = request.GET.get("cid")
    sid  = request.GET.get("sid")
    svc  = request.GET.get("svc")

    key, secret, base_url = _tool_env(tool)
    if not (key and secret and base_url):
        return HttpResponseBadRequest("Tool not configured")

    launch_url = settings.LTI_URL_BUILDER(tool, base_url, sub)

    source_id = f"{usr}_{grp}_{sub}"
    cache.set(f"lti:{source_id}", {"usr": usr, "grp": grp, "cid": cid, "sid": sid, "svc": svc, "tool": tool, "sub": sub}, timeout=3600)

    body = _build_lti_body(tool, source_id, sub, usr, grp, cid=cid, sid=sid, svc=svc)
    # OAuth 1.0 HMAC-SHA1 signing, body-style (like ims-lti)
    client = Client(key, client_secret=secret, signature_method="HMAC-SHA1", signature_type="BODY")
    unsigned = urlencode(body)
    _, headers, signed = client.sign(launch_url, http_method="POST", body=unsigned, headers={"Content-Type":"application/x-www-form-urlencoded"})
    params = dict(parse_qsl(signed))  # renderable key/vals

    # NOTE: if launch_url is http:// and you embed it under https://, browser will block it in an iframe.
    # Consider rendering a page that opens in a new tab for such tools, or get provider HTTPS.

    return render(request, "lti/auto_submit.html", {"action": launch_url, "params": params})

def outcome(request):
    # Minimal LTI POX outcome receiver (validates nothing; tighten to your needs)
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    # If you need to parse/verify the XML, do it here, then update your gradebook/service.
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<imsx_POXEnvelopeResponse xmlns="http://www.imsglobal.org/lis/oms1p0/pox">
  <imsx_POXHeader>
    <imsx_POXResponseHeaderInfo>
      <imsx_version>V1.0</imsx_version>
      <imsx_messageIdentifier>{uuid.uuid4()}</imsx_messageIdentifier>
      <imsx_statusInfo>
        <imsx_codeMajor>success</imsx_codeMajor>
        <imsx_severity>status</imsx_severity>
        <imsx_description>Processed</imsx_description>
        <imsx_messageRefIdentifier>{now}</imsx_messageRefIdentifier>
      </imsx_statusInfo>
    </imsx_POXResponseHeaderInfo>
  </imsx_POXHeader>
  <imsx_POXBody>
    <replaceResultResponse/>
  </imsx_POXBody>
</imsx_POXEnvelopeResponse>"""
    return HttpResponse(xml, content_type="text/xml")
