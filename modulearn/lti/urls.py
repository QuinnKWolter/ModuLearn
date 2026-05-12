from django.urls import path
from . import views

app_name = 'lti'

urlpatterns = [
    path('launch/', views.lti_launch, name='launch'),
    path('login/', views.lti13_login, name='login'),
    path('config/', views.lti_config, name='config'),
    path('jwks/', views.lti13_jwks, name='jwks'),
]