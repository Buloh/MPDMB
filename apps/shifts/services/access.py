"""Oprávnění a viditelnost zaměstnanců v plánu směn."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import QuerySet

from apps.accounts.roles import ROLE_ADMIN, ROLE_MANAGER
from apps.employees.models import Employee


def _group_names(user: AbstractBaseUser) -> set[str]:
    return set(user.groups.values_list("name", flat=True))


def can_manage_shift_plan(user: AbstractBaseUser) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    names = _group_names(user)
    return ROLE_ADMIN in names or ROLE_MANAGER in names


def employees_visible_for_shift_plan(user: AbstractBaseUser) -> QuerySet[Employee]:
    if not getattr(user, "is_authenticated", False):
        return Employee.objects.none()
    if can_manage_shift_plan(user):
        return Employee.objects.filter(is_active=True).order_by(
            "last_name", "first_name"
        )
    return Employee.objects.filter(user=user, is_active=True).order_by(
        "last_name", "first_name"
    )
