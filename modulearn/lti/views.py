from django.shortcuts import redirect
from django.conf import settings
from django.contrib.auth import login
from accounts.models import User
from django.http import JsonResponse, HttpResponse
from jwcrypto import jwk
import jwt
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from pylti1p3.contrib.django import (
    DjangoMessageLaunch,
    DjangoOIDCLogin,
    DjangoCacheDataStorage,
)
from pylti1p3.tool_config import ToolConfDict
import json

def lti_jwks(request):
    # Obtain the first available public key file from the LTI configuration
    platform_config = settings.LTI_CONFIG['https://saltire.lti.app/platform']
    with open(platform_config['public_key_file'], 'rb') as f:
        public_key_pem = f.read()
    key = jwk.JWK.from_pem(public_key_pem)
    public_key_json = key.export_public()
    public_key_dict = json.loads(public_key_json)
    return JsonResponse({'keys': [public_key_dict]})

@csrf_exempt
def lti_launch(request):
    print("Received POST data at lti_launch:", request.POST)
    tool_conf = ToolConfDict(settings.LTI_CONFIG)

    # Initialize storage instance
    launch_data_storage = DjangoCacheDataStorage()

    # Pass storage instance to Message Launch
    message_launch = DjangoMessageLaunch(
        request,
        tool_conf,
        launch_data_storage=launch_data_storage
    )

    test_session_value = request.session.get('test_session_key')
    print("Test session key on launch:", test_session_value)

    # Log the session key
    print("Session ID on launch:", request.session.session_key)

    # Decode the id_token to extract the nonce
    id_token = request.POST.get('id_token')
    if id_token:
        decoded_id_token = jwt.decode(id_token, options={"verify_signature": False})
        nonce = decoded_id_token.get('nonce')
        print("Nonce from id_token:", nonce)
    else:
        nonce = None
        print("No id_token found in POST data.")

    # Check if the nonce exists in the cache (Django cache)
    if nonce:
        cache_key = f'lti1p3-nonce-{nonce}'
        from django.core.cache import cache
        cache_nonce_value = cache.get(cache_key)
        print(f"Cache nonce value for {cache_key}:", cache_nonce_value)
    else:
        print("Nonce is None.")

    try:
        message_launch = message_launch.validate()
    except Exception as e:
        print(f"Nonce validation error: {e}")
        return HttpResponse(f"Nonce validation error: {e}", status=400)

    # Get launch data
    launch_data = message_launch.get_launch_data()
    print("Launch Data:", launch_data)
    
    # Authenticate the user
    sub = launch_data.get('sub')
    if not sub:
        return HttpResponse('Missing "sub" in launch data.', status=400)

    # Get or create user with basic info
    user, created = User.objects.get_or_create(username=sub)
    
    # Update user profile information if available
    if launch_data.get('email'):
        user.email = launch_data['email']
    if launch_data.get('given_name'):
        user.first_name = launch_data['given_name']
    if launch_data.get('family_name'):
        user.last_name = launch_data['family_name']
    
    # Set user role based on LTI roles
    roles = launch_data.get('https://purl.imsglobal.org/spec/lti/claim/roles', [])
    user.is_instructor = any('Instructor' in role for role in roles)
    user.is_student = any('Learner' in role for role in roles) or not user.is_instructor
    
    # Store LTI data with the user
    user.lti_data = launch_data
    user.save()
    
    login(request, user)

    # Redirect to the desired page
    return redirect('courses:course_list')

@csrf_exempt
def lti_login(request):
    print("Received data at lti_login:")
    print("Request method at lti_login:", request.method)
    print("GET parameters:", request.GET)
    print("POST parameters:", request.POST)
    tool_conf = ToolConfDict(settings.LTI_CONFIG)

    # Initialize storage instance
    launch_data_storage = DjangoCacheDataStorage()

    # Pass storage instance to OIDC login
    oidc_login = DjangoOIDCLogin(
        request,
        tool_conf,
        launch_data_storage=launch_data_storage
    )
    launch_url = request.build_absolute_uri(reverse('lti:launch')).replace("http://", "https://")
    print("Login Redirect URI (launch_url):", launch_url)

    # Set a test session variable
    request.session['test_session_key'] = 'session_active'
    request.session.save()  # Save the session explicitly

    print("Session ID on login:", request.session.session_key)

    response = oidc_login.redirect(launch_url)

    return response

def lti_config(request):
    # Build the tool configuration
    issuer = settings.LTI_CONFIG['issuer']
    oidc_login_url = request.build_absolute_uri(reverse('lti:login'))
    launch_url = request.build_absolute_uri(reverse('lti:launch'))
    jwks_url = request.build_absolute_uri(reverse('lti:jwks'))

    # Print each of the URLs for verification
    print("OIDC Login URL:", oidc_login_url)
    print("Launch URL:", launch_url)
    print("JWKS URL:", jwks_url)

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
