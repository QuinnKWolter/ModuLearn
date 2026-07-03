from django.urls import path

from . import views

app_name = "recruitment"

urlpatterns = [
    path("enter/<int:source_id>/", views.enter, name="enter"),
    path("prolific/<int:source_id>/", views.enter, name="prolific_enter"),
    path("consent/<uuid:session_uuid>/", views.consent, name="consent"),
    path("complete-current/<int:course_instance_id>/", views.complete_current, name="complete_current"),
    path("complete/<uuid:session_uuid>/", views.complete, name="complete"),
    path("thanks/<uuid:session_uuid>/", views.thank_you, name="thank_you"),
    path("already-completed/<uuid:session_uuid>/", views.already_completed, name="already_completed"),
    path("source/<int:course_instance_id>/create/", views.create_source, name="create_source"),
    path("source/<int:source_id>/export/", views.export_sessions, name="export_sessions"),
]
