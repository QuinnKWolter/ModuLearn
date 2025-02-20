from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Admin site
    path('admin/', admin.site.urls),

    # Custom Authentication URLs
    path('accounts/', include('accounts.urls', namespace='accounts')),

    # LTI URLs
    path('lti/', include('lti.urls')),

    # Courses and Modules
    path('courses/', include('courses.urls', namespace='courses')),

    # Dashboard
    path('dashboard/', include('dashboard.urls', namespace='dashboard')),

    # Static Pages
    path('', include('main.urls', namespace='main')),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
