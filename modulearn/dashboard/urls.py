from django.urls import path
from . import views
from .views import generate_course_auth_url, reset_course_authoring_password_view, proxy_course_authoring_x_login

app_name = 'dashboard'

urlpatterns = [
    path('student/', views.student_dashboard, name='student_dashboard'),
    path('instructor/', views.instructor_dashboard, name='instructor_dashboard'),
    path('legacy/', views.legacy_dashboard, name='legacy_dashboard'),
    path("api/generate_course_auth_url/", generate_course_auth_url, name="generate_course_auth_url"),
    path("api/proxy_x_login/", proxy_course_authoring_x_login, name="proxy_course_authoring_x_login"),
    path("api/reset_course_authoring_password/", reset_course_authoring_password_view, name="reset_course_authoring_password"),
    path("api/fetch_analytics_data/", views.fetch_analytics_data, name="fetch_analytics_data"),
    path("api/fetch_all_students_analytics/", views.fetch_all_students_analytics, name="fetch_all_students_analytics"),
    path("api/fetch_class_list/", views.fetch_class_list, name="fetch_class_list"),
    path("api/discover_course_ids/", views.discover_course_ids, name="discover_course_ids"),
    path("api/course_resources/<str:group_login>/", views.get_course_resources_api, name="get_course_resources_api"),
]
