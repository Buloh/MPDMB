"""Dlaždice přehledu podle role uživatele."""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth.models import AbstractBaseUser
from django.urls import reverse

from apps.accounts.roles import ROLE_ADMIN, ROLE_MANAGER, ROLE_READER


@dataclass(frozen=True)
class DashboardTile:
    key: str
    title: str
    description: str
    icon: str
    url_name: str | None = None
    url_path: str | None = None

    def resolve_url(self) -> str:
        if self.url_name:
            return reverse(self.url_name)
        return self.url_path or "#"


def _group_names(user: AbstractBaseUser) -> set[str]:
    if not getattr(user, "is_authenticated", False):
        return set()
    return set(user.groups.values_list("name", flat=True))


def can_manage_directory(user: AbstractBaseUser) -> bool:
    """Zaměstnanci, pracoviště a směny — administrátor nebo vedoucí (ne jen is_staff)."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    names = _group_names(user)
    return ROLE_ADMIN in names or ROLE_MANAGER in names


def can_see_admin_tile(user: AbstractBaseUser) -> bool:
    """Dlaždice Administrace – superuser nebo staff ve skupině administrátor."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return user.is_staff and ROLE_ADMIN in _group_names(user)


def nav_flags(user: AbstractBaseUser) -> dict[str, bool]:
    authenticated = getattr(user, "is_authenticated", False)
    directory = can_manage_directory(user) if authenticated else False
    has_employee = False
    if authenticated:
        from apps.employees.models import Employee

        has_employee = Employee.objects.filter(user_id=user.pk).exists()
    show_attendance = directory or has_employee
    show_leave = show_attendance
    show_ops = directory or show_attendance
    names = _group_names(user) if authenticated else set()
    is_reader_only = (
        authenticated
        and ROLE_READER in names
        and ROLE_ADMIN not in names
        and ROLE_MANAGER not in names
        and not directory
    )
    show_documents = False
    if authenticated and not is_reader_only:
        show_documents = directory or has_employee
    return {
        "show_employees": directory,
        "show_workplaces": directory,
        "show_shifts": directory,
        "show_attendance": show_attendance,
        "show_leave": show_leave,
        "show_ops": show_ops,
        "show_activities": directory,
        "show_technika": directory,
        "show_documents": show_documents,
        "show_admin": can_see_admin_tile(user) if authenticated else False,
        "show_help": authenticated,
    }


def tiles_for_user(user: AbstractBaseUser) -> list[DashboardTile]:
    flags = nav_flags(user)
    catalog = [
        DashboardTile(
            key="employees",
            title="Zaměstnanci",
            description="Evidence zaměstnanců, filtry a archivace.",
            icon="employees",
            url_name="employee_list",
        ),
        DashboardTile(
            key="workplaces",
            title="Pracoviště",
            description="Objekty a přiřazení zaměstnanců.",
            icon="workplaces",
            url_name="workplace_list",
        ),
        DashboardTile(
            key="ops",
            title="Provoz",
            description="Dlouhodobý plán, docházka a dovolená.",
            icon="ops",
            url_name="ops_hub",
        ),
        DashboardTile(
            key="activities",
            title="Činnost",
            description="Lokality a plán činností v rámci publikované směny.",
            icon="activities",
            url_name="activity_day",
        ),
        DashboardTile(
            key="technika",
            title="Technika",
            description="Vozidla, doklady STK/pojistka a odpovědné osoby.",
            icon="technika",
            url_name="vehicle_list",
        ),
        DashboardTile(
            key="documents",
            title="Dokumenty",
            description="Word šablony s placeholdery a uložené soubory.",
            icon="documents",
            url_name="documents_hub",
        ),
        DashboardTile(
            key="admin",
            title="Administrace",
            description="Účty, skupiny a systémová správa.",
            icon="admin",
            url_name="admin_hub",
        ),
        DashboardTile(
            key="help",
            title="Nápověda",
            description="Návody a vyhledávání v dokumentaci.",
            icon="help",
            url_name="help",
        ),
    ]
    key_map = {
        "employees": flags["show_employees"],
        "workplaces": flags["show_workplaces"],
        "ops": flags["show_ops"],
        "activities": flags["show_activities"],
        "technika": flags["show_technika"],
        "documents": flags["show_documents"],
        "admin": flags["show_admin"],
        "help": flags["show_help"],
    }
    return [tile for tile in catalog if key_map.get(tile.key)]


def ops_hub_tiles(user: AbstractBaseUser) -> list[DashboardTile]:
    """Poddlaždice rozcestníku Provoz."""
    flags = nav_flags(user)
    catalog = [
        DashboardTile(
            key="shifts",
            title="Dlouhodobý plán",
            description="Měsíční plán směn, publikace a typy směn.",
            icon="shifts",
            url_name="shift_month",
        ),
        DashboardTile(
            key="attendance",
            title="Docházka",
            description="Potvrzení práce a absence vůči plánu.",
            icon="attendance",
            url_name="attendance_month",
        ),
        DashboardTile(
            key="leave",
            title="Dovolená",
            description="Roční plán dovolené a zůstatky nároku.",
            icon="leave",
            url_name="leave_year",
        ),
    ]
    key_map = {
        "shifts": flags["show_shifts"],
        "attendance": flags["show_attendance"],
        "leave": flags["show_leave"],
    }
    return [tile for tile in catalog if key_map.get(tile.key)]
