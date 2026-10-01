"""Přehled publikovaných směn práce pro den (všechna pracoviště)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from apps.employees.models import Employee
from apps.employees.services import employment_for_day
from apps.shifts.models import Shift, ShiftType
from apps.shifts.services import employees_visible_for_shift_plan
from apps.workplaces.models import Workplace


def _is_work_shift(shift: Shift) -> bool:
    if not shift.shift_type_id:
        return True
    st = shift.shift_type
    return st.kind == ShiftType.Kind.WORK and st.counts_as_work


@dataclass(frozen=True)
class DayShiftRosterItem:
    employee: Employee
    workplace: Workplace
    shift: Shift
    starts_at: datetime
    ends_at: datetime
    display_code: str


def work_shifts_roster_for_day(
    user: AbstractBaseUser, day: date
) -> list[DayShiftRosterItem]:
    """Publikované work směny viditelných zaměstnanců v daný den (všechna WP)."""
    visible_ids = list(
        employees_visible_for_shift_plan(user).values_list("pk", flat=True)
    )
    if not visible_ids:
        return []
    tz = timezone.get_current_timezone()
    range_start = timezone.make_aware(datetime.combine(day, time.min), tz)
    range_end = timezone.make_aware(
        datetime.combine(day + timedelta(days=1), time.min), tz
    )
    shifts = (
        Shift.objects.filter(
            employee_id__in=visible_ids,
            status=Shift.Status.PUBLISHED,
            starts_at__gte=range_start,
            starts_at__lt=range_end,
        )
        .select_related("shift_type", "employee", "workplace")
        .order_by(
            "workplace__name",
            "employee__last_name",
            "employee__first_name",
            "starts_at",
        )
    )
    items: list[DayShiftRosterItem] = []
    for shift in shifts:
        if not _is_work_shift(shift):
            continue
        if employment_for_day(shift.employee, day) is None:
            continue
        code = (
            shift.shift_type.code
            if shift.shift_type_id and shift.shift_type.code
            else "—"
        )
        items.append(
            DayShiftRosterItem(
                employee=shift.employee,
                workplace=shift.workplace,
                shift=shift,
                starts_at=timezone.localtime(shift.starts_at),
                ends_at=timezone.localtime(shift.ends_at),
                display_code=code,
            )
        )
    return items


def workplace_shift_counts_for_day(
    user: AbstractBaseUser, day: date
) -> dict[int, int]:
    """Počet osob s publikovanou work směnou na pracovišti v daný den."""
    counts: dict[int, int] = {}
    seen: dict[int, set[int]] = {}
    for item in work_shifts_roster_for_day(user, day):
        wp_id = item.workplace.pk
        emp_set = seen.setdefault(wp_id, set())
        if item.employee.pk in emp_set:
            continue
        emp_set.add(item.employee.pk)
        counts[wp_id] = counts.get(wp_id, 0) + 1
    return counts
