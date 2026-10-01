"""Context processory jádra SYNERA."""

from apps.core.dashboard import nav_flags
from apps.core.version import APP_NAME, APP_TAGLINE, APP_TITLE, __version__


def app_branding(request):
    data = {
        "APP_NAME": APP_NAME,
        "APP_TITLE": APP_TITLE,
        "APP_TAGLINE": APP_TAGLINE,
        "APP_VERSION": __version__,
        "nav": {
            "show_employees": False,
            "show_workplaces": False,
            "show_shifts": False,
            "show_attendance": False,
            "show_leave": False,
            "show_ops": False,
            "show_documents": False,
            "show_admin": False,
            "show_help": False,
        },
    }
    if getattr(request, "user", None) is not None:
        data["nav"] = nav_flags(request.user)
    return data
