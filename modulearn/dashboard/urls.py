from django.urls import path
from . import views
from .views import generate_course_auth_url

app_name = 'dashboard'

urlpatterns = [
    path('student/', views.student_dashboard, name='student_dashboard'),
    # TEMP: route instructor dashboard to mockup; revert to views.instructor_dashboard when done
    path('instructor/', views.mockup_dashboard, name='instructor_dashboard'),
    path('mockup/', views.mockup_dashboard, name='mockup_dashboard'),
    path("api/generate_course_auth_url/", generate_course_auth_url, name="generate_course_auth_url"),
    path("api/fetch_analytics_data/", views.fetch_analytics_data, name="fetch_analytics_data"),
    path("api/fetch_all_students_analytics/", views.fetch_all_students_analytics, name="fetch_all_students_analytics"),
    path("api/fetch_class_list/", views.fetch_class_list, name="fetch_class_list"),
    path("api/fetch_user_groups/", views.fetch_user_groups, name="fetch_user_groups"),
    path("api/discover_course_ids/", views.discover_course_ids, name="discover_course_ids"),
    path("db-query/", views.db_query_interface, name="db_query_interface"),
]
