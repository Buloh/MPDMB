from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.core.dashboard import can_manage_directory, can_see_admin_tile, ops_hub_tiles, tiles_for_user
from apps.core.version import APP_NAME, __version__
from apps.employees.services import qualification_alerts_for_user
from apps.technika.services import vehicle_document_alerts_for_user

HELP_ROOT = Path(settings.BASE_DIR) / "help"


@login_not_required
@require_GET
def health(request):
    """Zdravotní kontrola bez citlivých údajů."""
    return JsonResponse(
        {
            "status": "ok",
            "service": APP_NAME,
            "version": __version__,
        }
    )


@require_GET
def home(request):
    """Přehled s dlaždicemi podle oprávnění uživatele."""
    tiles = tiles_for_user(request.user)
    return render(
        request,
        "core/home.html",
        {
            "title": "Přehled",
            "tiles": tiles,
            "show_limited_notice": len(tiles) <= 1,
            "qualification_alerts": qualification_alerts_for_user(request.user),
            "vehicle_document_alerts": vehicle_document_alerts_for_user(
                request.user
            ),
            "can_open_employees": can_manage_directory(request.user),
            "can_open_technika": can_manage_directory(request.user),
        },
    )


@require_GET
def ops_hub(request):
    """Rozcestník Provoz: směny, docházka, dovolená."""
    from apps.core.dashboard import nav_flags

    flags = nav_flags(request.user)
    if not flags.get("show_ops"):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied
    return render(
        request,
        "core/ops_hub.html",
        {
            "title": "Provoz",
            "tiles": ops_hub_tiles(request.user),
        },
    )


@require_GET
def admin_hub(request):
    """Rozcestník Administrace: účty, číselníky a odkazy do Django adminu."""
    from django.core.exceptions import PermissionDenied

    from apps.core.admin_hub import admin_hub_sections

    if not can_see_admin_tile(request.user):
        raise PermissionDenied
    return render(
        request,
        "core/admin_hub.html",
        {
            "title": "Administrace",
            "sections": admin_hub_sections(),
        },
    )


def _safe_help_path(relative: str) -> Path:
    relative = relative.replace("\\", "/").lstrip("/")
    if not relative:
        relative = "index.html"
    candidate = (HELP_ROOT / relative).resolve()
    root = HELP_ROOT.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise Http404("Soubor nápovědy nenalezen.") from exc
    if not candidate.is_file():
        raise Http404("Soubor nápovědy nenalezen.")
    return candidate


@require_GET
def help_index(request):
    """Úvodní stránka nápovědy."""
    path = _safe_help_path("index.html")
    return FileResponse(path.open("rb"), content_type="text/html; charset=utf-8")


@require_GET
def help_file(request, path: str):
    """Statický soubor nápovědy (HTML, CSS, JS, JSON)."""
    file_path = _safe_help_path(path)
    suffix = file_path.suffix.lower()
    content_types = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
    }
    content_type = content_types.get(suffix, "application/octet-stream")
    return FileResponse(file_path.open("rb"), content_type=content_type)
