from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from modulearn import views_lti, views_proxy

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

    # New LTI launcher and proxy routes
    path("lti/launch/", views_lti.launch, name="lti_launch"),
    path("lti/outcome/", views_lti.outcome, name="lti_outcome"),
    path("proxy/", views_proxy.http_get_proxy, name="http_get_proxy"),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
