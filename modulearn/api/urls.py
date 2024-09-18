from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    path('progress/', views.ProgressAPI.as_view(), name='progress_api'),
    path('grades/submit/', views.GradeSubmitAPI.as_view(), name='grade_submit_api'),
    path('content/import/', views.ContentImportAPI.as_view(), name='content_import_api'),
    path('modules/<int:module_id>/interact/', views.ModuleInteractAPI.as_view(), name='module_interact_api'),
]
