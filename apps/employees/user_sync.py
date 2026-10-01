"""Synchronizace jména a e-mailu ze zaměstnance na přihlašovací účet."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.employees.models import Employee


def sync_user_from_employee(employee: Employee) -> bool:
    """Zkopíruje jméno, příjmení a e-mail ze zaměstnance na účet. Vrací True při změně."""
    user = employee.user
    if user is None:
        return False
    new_first = (employee.first_name or "")[:150]
    new_last = (employee.last_name or "")[:150]
    new_email = (employee.email or "")[:254]
    if (
        user.first_name == new_first
        and user.last_name == new_last
        and user.email == new_email
    ):
        return False
    user.first_name = new_first
    user.last_name = new_last
    user.email = new_email
    user.save(update_fields=["first_name", "last_name", "email"])
    return True
