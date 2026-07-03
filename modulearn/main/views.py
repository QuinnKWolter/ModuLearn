from django.shortcuts import render

from recruitment.services.participants import participant_course_redirect


def home(request):
    redirect_response = participant_course_redirect(getattr(request, "user", None))
    if redirect_response:
        return redirect_response
    return render(request, 'main/home.html')


def info(request):
    return render(request, 'main/info.html')


def about(request):
    return info(request)


def contact(request):
    return info(request)
