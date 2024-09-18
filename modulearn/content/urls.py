from django.urls import path
from . import views

app_name = 'content'

urlpatterns = [
    path('render/<int:module_id>/', views.module_render, name='module_render'),
]
