from django.urls import path
from . import views
from .views import LTIOutcomesView, CaliperAnalyticsView

app_name = 'courses'

urlpatterns = [
    path('', views.course_list, name='course_list'),
    path('create/', views.create_course, name='create_course'),
    path('modules/<int:module_id>/render/', views.module_render, name='module_render'),
    path('modules/<int:module_id>/launch/', views.launch_iframe_module, name='launch_iframe_module'),
    path('modules/response/', views.log_lti_response, name='log_lti_response'),
    path('lti/outcomes/', LTIOutcomesView.as_view(), name='lti_outcomes'),
    path('caliper/analytics/', CaliperAnalyticsView.as_view(), name='caliper_analytics'),
    path('enroll/', views.enroll_with_code, name='enroll_with_code'),
    path('<str:course_id>/create_enrollment_code/', views.create_enrollment_code, name='create_enrollment_code'),
    path('<str:course_id>/', views.course_detail, name='course_detail'),
    path('<str:course_id>/unenroll/', views.unenroll, name='unenroll'),
    path('<str:course_id>/units/<int:unit_id>/modules/<int:module_id>/', views.module_detail, name='module_detail'),
]
