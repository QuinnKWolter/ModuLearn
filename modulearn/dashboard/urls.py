from django.urls import path
from . import views
from .views import generate_course_auth_url

app_name = 'dashboard'

urlpatterns = [
    path('student/', views.student_dashboard, name='student_dashboard'),
    path('instructor/', views.instructor_dashboard, name='instructor_dashboard'),
    path('mockup/', views.mockup_dashboard, name='mockup_dashboard'),
    path("api/generate_course_auth_url/", generate_course_auth_url, name="generate_course_auth_url"),
    path("api/fetch_analytics_data/", views.fetch_analytics_data, name="fetch_analytics_data"),
]
