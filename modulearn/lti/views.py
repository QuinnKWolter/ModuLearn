from django.shortcuts import render, redirect
from django.contrib.auth import login, get_user_model
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from .models import LTILaunch
from django.contrib import messages
from django.conf import settings
from django.http import HttpResponse
from django.contrib.auth.backends import ModelBackend

User = get_user_model()

@csrf_exempt  # LTI launches may not include CSRF tokens
def lti_launch(request):
    """
    Handles LTI launch requests from Canvas.
    """
    if request.method == 'POST':
        # Extract LTI parameters
        lti_user_id = request.POST.get('user_id')
        email = request.POST.get('lis_person_contact_email_primary')
        first_name = request.POST.get('lis_person_name_given')
        last_name = request.POST.get('lis_person_name_family')
        roles = request.POST.get('roles', '')
        is_instructor = 'Instructor' in roles

        # Authenticate or create user
        user, created = User.objects.get_or_create(username=lti_user_id)
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.is_instructor = is_instructor
        user.is_student = not is_instructor
        user.save()

        # Log in the user
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user)

        # Save LTI launch data if needed
        LTILaunch.objects.create(
            user=user,
            id_token=request.POST.get('id_token', ''),
            state=request.POST.get('state', ''),
            nonce=request.POST.get('nonce', ''),
            # Include other fields as necessary
        )

        # Redirect to appropriate dashboard
        if is_instructor:
            return redirect('dashboard:instructor_dashboard')
        else:
            return redirect('dashboard:student_dashboard')
    else:
        return HttpResponse('Invalid LTI launch request.', status=400)
