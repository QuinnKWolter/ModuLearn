from django.urls import path
from . import views

app_name = 'main'

urlpatterns = [
    path('', views.home, name='home'),
    path('home/overview/', views.home, {'audience': 'overview'}, name='home_overview'),
    path('home/students/', views.home, {'audience': 'students'}, name='home_students'),
    path('home/teachers/', views.home, {'audience': 'teachers'}, name='home_teachers'),
    path('home/researchers/', views.home, {'audience': 'researchers'}, name='home_researchers'),
    path('info/', views.info, name='info'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
]
