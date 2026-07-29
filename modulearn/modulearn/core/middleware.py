from django.conf import settings
from django.utils import translation
from django.utils.cache import patch_vary_headers


class QueryStringLanguageMiddleware:
    """Allow any page to opt into a UI language with ?lang=<code>."""

    param_name = "lang"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language_code = self._clean_language_code(request.GET.get(self.param_name))
        if language_code:
            translation.activate(language_code)
            request.LANGUAGE_CODE = language_code

        response = self.get_response(request)

        if language_code:
            response.set_cookie(
                settings.LANGUAGE_COOKIE_NAME,
                language_code,
                max_age=getattr(settings, "LANGUAGE_COOKIE_AGE", None),
                path=getattr(settings, "LANGUAGE_COOKIE_PATH", "/"),
                domain=getattr(settings, "LANGUAGE_COOKIE_DOMAIN", None),
                secure=getattr(settings, "LANGUAGE_COOKIE_SECURE", False),
                httponly=getattr(settings, "LANGUAGE_COOKIE_HTTPONLY", False),
                samesite=getattr(settings, "LANGUAGE_COOKIE_SAMESITE", "Lax"),
            )
            response.headers.setdefault("Content-Language", language_code)
            patch_vary_headers(response, ("Cookie",))

        return response

    @staticmethod
    def _clean_language_code(value):
        if not value:
            return None
        requested = str(value).strip().lower().replace("_", "-")
        if not requested:
            return None

        allowed = {code.lower(): code for code, _label in settings.LANGUAGES}
        if requested in allowed:
            return allowed[requested]

        primary_subtag = requested.split("-", 1)[0]
        return allowed.get(primary_subtag)
