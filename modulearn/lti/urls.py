from django.urls import path
from . import views

app_name = 'lti'

urlpatterns = [
    path('launch/', views.lti_launch, name='launch'),
    path('login/', views.lti13_login, name='login'),
    path('config/', views.lti_config, name='config'),
    path('jwks/', views.lti13_jwks, name='jwks'),
    path('setup-details/', views.lti_setup_details, name='setup_details'),
    path('platform-registration/', views.lti13_platform_registration, name='platform_registration'),
]
