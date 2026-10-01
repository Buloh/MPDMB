"""Společné kontroly oprávnění pro provozní moduly."""

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def staff_required(view_func):
    """Povolí view jen přihlášenému uživateli se statusem staff."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_staff:
            raise PermissionDenied("Nemáte oprávnění k této akci.")
        return view_func(request, *args, **kwargs)

    return _wrapped
