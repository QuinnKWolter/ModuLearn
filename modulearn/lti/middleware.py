from django.shortcuts import redirect
from django.urls import reverse
from django.contrib.auth import get_user_model

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