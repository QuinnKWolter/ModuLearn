"""Normalize mount-boundary slashes without redirecting POST bodies."""
from uuid import uuid4

from django.conf import settings
from .logging_utils import request_id_context


class RequestDiagnosticsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info.startswith('//'):
            request.path_info = '/' + request.path_info.lstrip('/')
            request.META['PATH_INFO'] = request.path_info
            prefix = settings.FORCE_SCRIPT_NAME or request.META.get('SCRIPT_NAME', '')
            request.path = prefix.rstrip('/') + request.path_info
        request.request_id = uuid4().hex
        context = request_id_context.set(request.request_id)
        try:
            response = self.get_response(request)
            response['X-Request-ID'] = request.request_id
            return response
        finally:
            request_id_context.reset(context)
