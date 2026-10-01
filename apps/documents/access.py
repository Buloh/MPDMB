"""Kontroly oprávnění modulu Dokumenty."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser

from apps.accounts.roles import ROLE_ADMIN, ROLE_READER
from apps.core.dashboard import can_manage_directory
from apps.employees.models import Employee

from .models import StoredDocument


def _group_names(user: AbstractBaseUser) -> set[str]:
    if not getattr(user, "is_authenticated", False):
        return set()
    return set(user.groups.values_list("name", flat=True))


def can_manage_templates(user: AbstractBaseUser) -> bool:
    """Šablony: zakládat, vkládat placeholdery, nové verze."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return ROLE_ADMIN in _group_names(user)


def can_manage_stored_documents(user: AbstractBaseUser) -> bool:
    """Generovat / nahrávat / archivovat dokumenty zaměstnanců a techniky."""
    return can_manage_directory(user)


def can_read_templates(user: AbstractBaseUser) -> bool:
    """Číst šablony (pro generování)."""
    return can_manage_templates(user) or can_manage_stored_documents(user)


def linked_employee(user: AbstractBaseUser) -> Employee | None:
    if not getattr(user, "is_authenticated", False):
        return None
    return Employee.objects.filter(user_id=user.pk).first()


def can_view_own_documents(user: AbstractBaseUser) -> bool:
    """Zaměstnanec smí číst vlastní uložené dokumenty (ne čtenář)."""
    if not getattr(user, "is_authenticated", False):
        return False
    if can_manage_directory(user) or can_manage_templates(user):
        return linked_employee(user) is not None
    names = _group_names(user)
    if ROLE_READER in names:
        return False
    return linked_employee(user) is not None


def can_access_documents(user: AbstractBaseUser) -> bool:
    if can_manage_stored_documents(user):
        return True
    return can_view_own_documents(user)


def can_view_stored_document(user: AbstractBaseUser, doc: StoredDocument) -> bool:
    if can_manage_stored_documents(user):
        return True
    employee = linked_employee(user)
    if employee is None:
        return False
    return doc.employee_id == employee.pk


def can_view_employee_documents(user: AbstractBaseUser, employee: Employee) -> bool:
    if can_manage_stored_documents(user):
        return True
    linked = linked_employee(user)
    return linked is not None and linked.pk == employee.pk
