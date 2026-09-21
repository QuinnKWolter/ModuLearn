from django.contrib import admin
import re
from urllib.parse import urlsplit

from django.urls import path, include, re_path
from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.views.static import serve as serve_media
from modulearn import views_lti, views_proxy

urlpatterns = [
    # Admin site
    path('admin/', admin.site.urls),

    # Language selection
    path('i18n/', include('django.conf.urls.i18n')),

    # Custom Authentication URLs
    path('accounts/', include('accounts.urls', namespace='accounts')),

    # LTI URLs
    path('lti/', include('lti.urls')),

    # Courses and Modules
    path('courses/', include('courses.urls', namespace='courses')),

    # Dashboard
    path('dashboard/', include('dashboard.urls', namespace='dashboard')),

    # Research recruitment
    path('r/', include('recruitment.urls', namespace='recruitment')),

    # Static Pages
    path('', include('main.urls', namespace='main')),

    # Tool launch endpoint (distinct from Canvas LTI at /lti/launch/)
    path("lti/tool-launch/", views_lti.launch, name="lti_launch"),
    path("lti/outcome/", views_lti.outcome, name="lti_outcome"),
    path("lti/health/", views_lti.health, name="lti_health"),
    
    # HTTP proxy for mixed content (HTTP tools in HTTPS iframe)
    path("proxy/", views_proxy.http_get_proxy, name="http_get_proxy"),  # query-mode for compatibility
    path("proxy/<path:rest>", views_proxy.http_get_proxy_path, name="http_get_proxy_path"),

    # PCRS assigns these legacy result images dynamically as root-relative URLs.
    path(
        "mgrids/static/problems/img/<str:filename>",
        views_proxy.pcrs_feedback_asset,
        name="pcrs_feedback_asset",
    ),
    
    # Catch-all for external activity API calls (e.g., /pcex/api/track/activity)
    # These are relative URLs from activities that expect to be on pawscomp2.sis.pitt.edu
    path("pcex/<path:rest>", views_proxy.forward_to_adapt2, name="forward_pcex"),

    # ACOS-hosted PCEX pages sometimes emit root-relative requests before
    # browser-side URL rewriting can normalize them.
    path(
        "pitt/acos-pcex/<path:rest>",
        views_proxy.forward_acos_pcex,
        {"prefix": "pitt/acos-pcex"},
        name="forward_acos_pcex_pitt",
    ),
    path(
        "html/acos-pcex/<path:rest>",
        views_proxy.forward_acos_pcex,
        {"prefix": "html/acos-pcex"},
        name="forward_acos_pcex_html",
    ),
    path(
        "static/acos-pcex/<path:rest>",
        views_proxy.forward_acos_pcex,
        {"prefix": "static/acos-pcex"},
        name="forward_acos_pcex_static",
    ),
    path(
        "static/acos-pcex-examples/<path:rest>",
        views_proxy.forward_acos_pcex,
        {"prefix": "static/acos-pcex-examples"},
        name="forward_acos_pcex_examples_static",
    ),
    
    # Catch-all for CBUM (User Model) API calls (e.g., /cbum/um?app=46&act=...)
    # These are relative URLs from activities that expect to be on pawscomp2.sis.pitt.edu
    path("cbum/<path:rest>", views_proxy.forward_cbum, name="forward_cbum"),
]

if (settings.DEBUG or getattr(settings, 'SERVE_MEDIA_FILES', False)) and settings.MEDIA_URL not in ('', '/'):
    media_path = urlsplit(settings.MEDIA_URL).path.lstrip('/')
    script_name = (settings.FORCE_SCRIPT_NAME or '').strip('/')
    if script_name and media_path.startswith(f'{script_name}/'):
        media_path = media_path[len(script_name) + 1:]
    if media_path:
        urlpatterns += [
            re_path(
                rf'^{re.escape(media_path)}(?P<path>.*)$',
                serve_media,
                {'document_root': settings.MEDIA_ROOT},
            ),
        ]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
