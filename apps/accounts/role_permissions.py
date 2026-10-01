"""Matice Django oprávnění pro role (skupiny) podle názvu."""

from __future__ import annotations

from django.contrib.auth.models import Group, Permission

from apps.accounts.roles import (
    ALL_ROLES,
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
    ROLE_MANAGER,
    ROLE_READER,
)

# Provozní aplikace — plné CRUD (vedoucí)
_OPS_APPS = (
    "employees",
    "workplaces",
    "shifts",
    "attendance",
    "leave",
    "activities",
    "technika",
    "documents",
)

# Přehledy (view) pro zaměstnance / čtenáře
# documents záměrně chybí: čtenář nic; zaměstnanec jen vlastní přes aplikační kontrolu
_VIEW_APPS = (
    "employees",
    "workplaces",
    "shifts",
    "attendance",
    "leave",
    "activities",
    "technika",
)

# Vedoucí nesmí měnit Word šablony (jen číst a generovat z nich)
_MANAGER_TEMPLATE_WRITE = (
    "documents.add_documenttemplate",
    "documents.change_documenttemplate",
    "documents.delete_documenttemplate",
    "documents.add_documenttemplateversion",
    "documents.change_documenttemplateversion",
    "documents.delete_documenttemplateversion",
)


def _codenames_for_apps(
    app_labels: tuple[str, ...], *, prefixes: tuple[str, ...]
) -> set[str]:
    """Vrátí množinu 'app_label.codename'."""
    qs = Permission.objects.filter(content_type__app_label__in=app_labels)
    out: set[str] = set()
    for perm in qs.select_related("content_type"):
        if any(perm.codename.startswith(p) for p in prefixes):
            out.add(f"{perm.content_type.app_label}.{perm.codename}")
    return out


def _all_permission_keys() -> set[str]:
    return {
        f"{p.content_type.app_label}.{p.codename}"
        for p in Permission.objects.select_related("content_type")
    }


def permission_keys_for_role(role_name: str) -> set[str]:
    """Očekávané klíče oprávnění (app.codename) pro danou roli."""
    if role_name == ROLE_ADMIN:
        return _all_permission_keys()

    if role_name == ROLE_MANAGER:
        keys = _codenames_for_apps(
            _OPS_APPS, prefixes=("add_", "change_", "delete_", "view_")
        )
        keys.add("activities.export_activity_plan")
        keys -= set(_MANAGER_TEMPLATE_WRITE)
        return keys

    if role_name in (ROLE_EMPLOYEE, ROLE_READER):
        return _codenames_for_apps(_VIEW_APPS, prefixes=("view_",))

    return set()


def sync_role_group_permissions() -> dict[str, int]:
    """Nastaví permissions skupin podle názvu role. Vrací {role: počet práv}."""
    counts: dict[str, int] = {}
    for role_name in ALL_ROLES:
        group, _ = Group.objects.get_or_create(name=role_name)
        if role_name == ROLE_ADMIN:
            perms = list(Permission.objects.all())
        else:
            keys = permission_keys_for_role(role_name)
            perms = []
            for key in keys:
                app_label, codename = key.split(".", 1)
                try:
                    perms.append(
                        Permission.objects.get(
                            content_type__app_label=app_label, codename=codename
                        )
                    )
                except Permission.DoesNotExist:
                    continue
        group.permissions.set(perms)
        counts[role_name] = len(perms)
    return counts
