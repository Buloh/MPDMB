"""Společné konstanty, oprávnění a pomocné funkce docházky."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import QuerySet
from django.utils import timezone

from apps.core.models import AuditEvent
from apps.employees.models import Employee
from apps.shifts.fund import month_day_list
from apps.shifts.models import Shift, ShiftType
from apps.shifts.services import (
    can_manage_shift_plan,
    employees_visible_for_shift_plan,
)
from apps.workplaces.models import Workplace


class AttendanceConflictError(ValidationError):
    """Konflikt docházky (souběh, verze, vzájemné vyloučení)."""


MISSING_EMPLOYMENT_MSG = (
    "U zaměstnance chybí aktivní pracovní vztah k datu směny. "
    "Doplňte den nástupu na kartě zaměstnance."
)
MISSING_EMPLOYMENT_ADHOC_MSG = (
    "U zaměstnance chybí aktivní pracovní vztah k zvolenému dni. "
    "Doplňte den nástupu na kartě zaměstnance."
)
MISSING_EMPLOYMENT_CODE = "missing_employment"


def _audit(user, operation: str, object_type: str, object_id: str, detail: str = "") -> None:
    AuditEvent.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        operation=operation,
        object_type=object_type,
        object_id=str(object_id),
        detail=detail,
    )


def can_manage_attendance(user: AbstractBaseUser) -> bool:
    return can_manage_shift_plan(user)


def employees_visible_for_attendance(user: AbstractBaseUser) -> QuerySet[Employee]:
    return employees_visible_for_shift_plan(user)


def can_access_employee_attendance(user: AbstractBaseUser, employee: Employee) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if can_manage_attendance(user):
        return True
    return bool(employee.user_id and employee.user_id == user.pk)


def workplaces_for_employee_day(employee: Employee, day: date):
    """Aktivní přiřazení pracovišť v daný den; fallback všech aktivních."""
    qs = (
        Workplace.objects.filter(
            is_active=True,
            employee_assignments__employee=employee,
            employee_assignments__valid_from__lte=day,
        )
        .filter(
            models.Q(employee_assignments__valid_to__isnull=True)
            | models.Q(employee_assignments__valid_to__gte=day)
        )
        .distinct()
        .order_by("name")
    )
    if qs.exists():
        return qs
    return Workplace.objects.filter(is_active=True).order_by("name")


def is_published_work_shift(shift: Shift) -> bool:
    if shift.status != Shift.Status.PUBLISHED:
        return False
    if not shift.shift_type_id:
        return True
    st = shift.shift_type
    return st.kind == ShiftType.Kind.WORK and st.counts_as_work


def is_published_leave_shift(shift: Shift) -> bool:
    if shift.status != Shift.Status.PUBLISHED:
        return False
    if not shift.shift_type_id:
        return False
    return shift.shift_type.kind == ShiftType.Kind.LEAVE


def is_attendance_matrix_shift(shift: Shift) -> bool:
    """Směny práce i dovolené v měsíční matici docházky."""
    return is_published_work_shift(shift) or is_published_leave_shift(shift)


def shift_local_day(shift: Shift) -> date:
    return timezone.localtime(shift.starts_at).date()


def published_work_shifts_for_month(
    employee: Employee, year: int, month: int
) -> list[Shift]:
    days = month_day_list(year, month)
    if not days:
        return []
    tz = timezone.get_current_timezone()
    range_start = timezone.make_aware(datetime.combine(days[0], time.min), tz)
    range_end = timezone.make_aware(
        datetime.combine(days[-1] + timedelta(days=1), time.min), tz
    )
    qs = (
        Shift.objects.filter(
            employee=employee,
            status=Shift.Status.PUBLISHED,
            starts_at__gte=range_start,
            starts_at__lt=range_end,
        )
        .select_related("shift_type", "workplace", "employee")
        .order_by("starts_at")
    )
    return [s for s in qs if is_published_work_shift(s)]


def _proposed_break_minutes(shift: Shift) -> int:
    if shift.shift_type_id:
        return int(shift.shift_type.break_minutes)
    return 0

