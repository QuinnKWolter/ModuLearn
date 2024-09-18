# lti/urls.py

from django.urls import path
from . import views

app_name = 'lti'

urlpatterns = [
    path('launch/', views.lti_launch, name='launch'),
]
