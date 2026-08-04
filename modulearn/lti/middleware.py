from django.shortcuts import redirect
from django.urls import reverse
from django.contrib.auth import get_user_model
from lti.models import LTIUserIdentity

User = get_user_model()

class LTIAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if this is an LTI session
        is_lti_launch = request.session.get('is_lti_launch', False)
        
        if is_lti_launch and not request.user.is_authenticated:
            # Try to get the user from the stored Canvas ID
            canvas_user_id = request.session.get('canvas_user_id')
            lti_platform_user_id = request.session.get('lti_platform_user_id')
            lti_issuer = request.session.get('lti_issuer')
            lti_client_id = request.session.get('lti_client_id', '')
            if lti_platform_user_id and lti_issuer:
                try:
                    identity = LTIUserIdentity.objects.select_related('user').get(
                        issuer=lti_issuer,
                        client_id=lti_client_id,
                        subject=lti_platform_user_id,
                    )
                    request.user = identity.user
                    target_url = request.session.get('lti_target_url')
                    if target_url and request.path != target_url:
                        return redirect(target_url)
                except LTIUserIdentity.DoesNotExist:
                    pass
            if canvas_user_id:
                try:
                    user = User.objects.get(canvas_user_id=canvas_user_id)
                    request.user = user
                    # Don't redirect if we're already going to the target URL
                    target_url = request.session.get('lti_target_url')
                    if target_url and request.path != target_url:
                        return redirect(target_url)
                except User.DoesNotExist:
                    pass

        response = self.get_response(request)
        return response
