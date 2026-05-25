from django.shortcuts import render


def home(request):
    return render(request, 'main/home.html')


def info(request):
    return render(request, 'main/info.html')


def about(request):
    return info(request)


def contact(request):
    return info(request)
