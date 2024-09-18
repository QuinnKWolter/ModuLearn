from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Admin site
    path('admin/', admin.site.urls),

    # Authentication URLs
    path('accounts/', include('django.contrib.auth.urls')),
    path('accounts/', include('accounts.urls', namespace='accounts')),

    # LTI URLs
    path('lti/', include('lti.urls', namespace='lti')),

    # Courses and Modules
    path('courses/', include('courses.urls', namespace='courses')),

    # Dashboard
    path('dashboard/', include('dashboard.urls', namespace='dashboard')),

    # Content Rendering
    path('content/', include('content.urls', namespace='content')),

    # API Endpoints
    path('api/', include('api.urls', namespace='api')),

    # Static Pages
    path('', include('main.urls', namespace='main')),
]
