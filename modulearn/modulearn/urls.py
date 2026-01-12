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

    # Tool launch endpoint (distinct from Canvas LTI at /lti/launch/)
    path("lti/tool-launch/", views_lti.launch, name="lti_launch"),
    path("lti/outcome/", views_lti.outcome, name="lti_outcome"),
    path("lti/health/", views_lti.health, name="lti_health"),
    
    # HTTP proxy for mixed content (HTTP tools in HTTPS iframe)
    path("proxy/", views_proxy.http_get_proxy, name="http_get_proxy"),  # query-mode for compatibility
    path("proxy/<path:rest>", views_proxy.http_get_proxy_path, name="http_get_proxy_path"),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
