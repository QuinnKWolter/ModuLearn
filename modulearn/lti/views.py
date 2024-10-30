from django.shortcuts import redirect
from django.conf import settings
from django.contrib.auth import login, authenticate
from django.contrib.auth.models import User
from django.http import JsonResponse
from jwcrypto import jwk
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
import json

# Import Django-specific classes from PyLTI1p3
from pylti1p3.contrib.django import (
    DjangoMessageLaunch,
    DjangoOIDCLogin,
    DjangoCacheDataStorage,
)
from pylti1p3.tool_config import ToolConfDict

def lti_jwks(request):
    with open(settings.LTI_CONFIG['public_key_file'], 'rb') as f:
        public_key_pem = f.read()
    key = jwk.JWK.from_pem(public_key_pem)
    public_key_json = key.export_public()
    public_key_dict = json.loads(public_key_json)
    return JsonResponse({'keys': [public_key_dict]})

@csrf_exempt  # Exempt from CSRF checks if necessary
def lti_launch(request):
    # Use ToolConfDict to hold your LTI configuration
    tool_conf = ToolConfDict(settings.LTI_CONFIG)
    storage = DjangoCacheDataStorage()
    # Use DjangoMessageLaunch for Django integration
    message_launch = DjangoMessageLaunch(request, tool_conf, cache_storage=storage)
    # Validate and get launch data
    message_launch = message_launch.validate()
    launch_data = message_launch.get_launch_data()

    # Authenticate the user or create a new one
    sub = launch_data['sub']
    user = authenticate(request, sub=sub)
    if user is None:
        user = User.objects.create_user(username=sub)
    login(request, user)

    # Store launch data in session
    request.session['launch_data'] = launch_data

    # Redirect to the desired view
    return redirect('courses:course_list')

@csrf_exempt
def lti_login(request):
    # Use ToolConfDict to hold your LTI configuration
    tool_conf = ToolConfDict(settings.LTI_CONFIG)
    # Use DjangoOIDCLogin for Django integration
    oidc_login = DjangoOIDCLogin(request, tool_conf)
    # Redirect to the launch URL after OIDC login
    return oidc_login\
        .enable_check_cookies()\
        .redirect(reverse('lti:launch'))

def lti_config(request):
    # Build the tool configuration
    from django.urls import reverse
    issuer = settings.LTI_CONFIG['issuer']
    oidc_login_url = request.build_absolute_uri(reverse('lti:login'))
    launch_url = request.build_absolute_uri(reverse('lti:launch'))
    jwks_url = request.build_absolute_uri(reverse('lti:jwks'))

    tool_config = {
        "title": "ModuLearn",
        "description": "An LTI 1.3 tool built with Django.",
        "scopes": [
            "https://purl.imsglobal.org/spec/lti-ags/scope/score",
            "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem",
            # Add other scopes as needed
        ],
        "extensions": [],
        "public_jwk_url": jwks_url,
        "custom_fields": {},
        "target_link_uri": launch_url,
        "oidc_initiation_url": oidc_login_url,
        "custom_parameters": {},
    }

    return JsonResponse(tool_config)
