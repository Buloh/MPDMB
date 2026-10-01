"""České popisky Django oprávnění a úklid osiřelých ContentType."""

from __future__ import annotations

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import translation

_ACTION_PREFIXES = (
    ("add_", "Přidat: "),
    ("change_", "Změnit: "),
    ("delete_", "Smazat: "),
    ("view_", "Zobrazit: "),
)

_SPECIAL_CODENAMES = {
    "export_activity_plan": "Exportovat plán činností",
}


def czech_name_for_permission(perm: Permission) -> str | None:
    """Vrátí cílový český název, nebo None pokud ponechat beze změny."""
    if perm.codename in _SPECIAL_CODENAMES:
        return _SPECIAL_CODENAMES[perm.codename]

    model = perm.content_type.model_class()
    if model is None:
        return None

    with translation.override("cs"):
        verbose = str(model._meta.verbose_name)

    for prefix, label in _ACTION_PREFIXES:
        if perm.codename.startswith(prefix):
            return f"{label}{verbose}"
    return None


def refresh_permission_names() -> int:
    """Přepíše Permission.name z aktuálního verbose_name modelu. Vrací počet změn."""
    updated = 0
    for perm in Permission.objects.select_related("content_type").iterator():
        new_name = czech_name_for_permission(perm)
        if new_name is None or perm.name == new_name:
            continue
        perm.name = new_name
        perm.save(update_fields=["name"])
        updated += 1
    return updated


def delete_orphaned_content_types() -> int:
    """Smaže ContentType bez živého modelu (včetně navázaných Permission)."""
    deleted = 0
    for ct in list(ContentType.objects.all()):
        if ct.model_class() is not None:
            continue
        ContentType.objects.filter(pk=ct.pk).delete()
        deleted += 1
    return deleted
