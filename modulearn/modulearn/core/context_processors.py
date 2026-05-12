from datetime import datetime

from .navigation import build_navigation
from .roles import get_user_role_snapshot
from modulearn.integrations.config import get_script_name


def app_shell(request):
    """Shared shell context for all templates."""
    role_snapshot = get_user_role_snapshot(getattr(request, "user", None))
    return {
        "year": datetime.now().year,
        "app_script_name": get_script_name(),
        "primary_navigation": build_navigation(request),
        "effective_is_student": role_snapshot["effective_is_student"],
        "effective_is_instructor": role_snapshot["effective_is_instructor"],
    }
