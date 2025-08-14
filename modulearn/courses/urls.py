from django.urls import path
from . import views
from .views import LTIOutcomesView, CaliperAnalyticsView

app_name = 'courses'

urlpatterns = [
    path('', views.course_list, name='course_list'),
    path('check-group-name/', views.check_group_name, name='check_group_name'),
    path('create-semester-course/', views.create_semester_course, name='create_semester_course'),
    path('create/', views.create_course, name='create_course'),
    path('update-module-progress/<int:module_id>/', views.update_module_progress, name='update_module_progress'),
    # Instructor preview (no tracking) route
    path('modules/<int:module_id>/launch/', views.preview_iframe_module, name='preview_iframe_module'),
    path('modules/response/', views.log_lti_response, name='log_lti_response'),
    path('lti/outcomes/', LTIOutcomesView.as_view(), name='lti_outcomes'),
    path('caliper/analytics/', CaliperAnalyticsView.as_view(), name='caliper_analytics'),
    path('enroll/', views.enroll_with_code, name='enroll_with_code'),
    path('<str:course_instance_id>/enrollments/', views.get_course_enrollments, name='get_course_enrollments'),
    path('<str:course_instance_id>/bulk-enroll/', views.bulk_enroll_students, name='bulk_enroll_students'),
    path('enrollment/<int:enrollment_id>/remove/', views.remove_enrollment, name='remove_enrollment'),
    # Create enrollment code for a specific course instance
    path('instance/<int:course_instance_id>/create_enrollment_code/', views.create_enrollment_code, name='create_enrollment_code'),
    path('<str:course_id>/create-instance/', views.create_course_instance, name='create_course_instance'),
    path('<str:course_id>/details/', views.course_details, name='course_details'),
    path('<str:course_id>/delete/', views.delete_course, name='delete_course'),
    path('instance/<int:instance_id>/', views.course_detail, name='course_detail'),
    path('instance/<int:instance_id>/modules/<int:module_id>/launch/', 
         views.launch_iframe_module, 
         name='launch_iframe_module'),
    path('instance/<int:instance_id>/units/<int:unit_id>/modules/<int:module_id>/', views.module_detail, name='module_detail'),
]
