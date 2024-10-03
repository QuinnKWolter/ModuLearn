from django.urls import path
from . import views

app_name = 'courses'

urlpatterns = [
    path('', views.course_list, name='course_list'),
    path('<int:course_id>/', views.course_detail, name='course_detail'),
    path('<int:course_id>/units/<int:unit_id>/modules/<int:module_id>/', views.module_detail, name='module_detail'),
    path('modules/<int:module_id>/render/', views.module_render, name='module_render'),
    path('<int:course_id>/unenroll/', views.unenroll, name='unenroll'),
]
