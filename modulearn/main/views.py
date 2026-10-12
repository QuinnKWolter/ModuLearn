from django.shortcuts import render

from recruitment.services.participants import participant_course_redirect
from modulearn.core.roles import get_user_role_snapshot


def home(request, audience=None):
    redirect_response = participant_course_redirect(getattr(request, "user", None))
    if redirect_response:
        return redirect_response
    # Account roles determine the landing view, including legacy audience URLs.
    # Saved audience preferences must not override the signed-in user's role.
    role = get_user_role_snapshot(request.user)
    audience = 'teachers' if role['effective_is_instructor'] else 'students' if role['effective_is_student'] else 'overview'
    return render(request, 'main/home.html', {'home_audience': audience})


def info(request):
    return render(request, 'main/info.html')


def about(request):
    return info(request)


def contact(request):
    return info(request)
