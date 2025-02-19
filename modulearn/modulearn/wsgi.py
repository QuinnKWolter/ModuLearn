"""
WSGI config for modulearn project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'modulearn.settings')

# Create the WSGI application
application = get_wsgi_application()

# Add URL prefix handling
from django.conf import settings
if hasattr(settings, 'FORCE_SCRIPT_NAME'):
    application = lambda environ, start_response: application(
        dict(environ, SCRIPT_NAME=settings.FORCE_SCRIPT_NAME), start_response
    )
