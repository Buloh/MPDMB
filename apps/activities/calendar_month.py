"""Měsíční kalendář pro plán činností (sync s polem Den)."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from apps.employees.models import Employee
from apps.employees.services import employment_for_day
from apps.shifts.models import Shift, ShiftType
from apps.shifts.services import employees_visible_for_shift_plan
from apps.workplaces.models import Workplace

from .models import ActivityItem

WEEKDAY_HEADERS = ("Po", "Út", "St", "Čt", "Pá", "So", "Ne")

_MONTH_NAMES_CS = (
    "",
    "leden",
    "únor",
    "březen",
    "duben",
    "květen",
    "červen",
    "červenec",
    "srpen",
    "září",
    "říjen",
    "listopad",
    "prosinec",
)


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def _shift_day(shift: Shift) -> date:
    return timezone.localtime(shift.starts_at).date()


def _is_work_shift(shift: Shift) -> bool:
    if not shift.shift_type_id:
        return True
    st = shift.shift_type
    return st.kind == ShiftType.Kind.WORK and st.counts_as_work


def activity_month_markers(
    user: AbstractBaseUser,
    workplace: Workplace | None,
    year: int,
    month: int,
    *,
    employee: Employee | None = None,
) -> dict[date, dict[str, Any]]:
    """Značky dnů: has_shift / has_plan / shift_count napříč pracovišti.

    Pracoviště desku neomezuje tečky. Při vybraném zaměstnanci jen jeho směny.
    """
    markers: dict[date, dict[str, Any]] = {}
    visible_ids = list(
        employees_visible_for_shift_plan(user).values_list("pk", flat=True)
    )
    if not visible_ids:
        return markers
    if employee is not None:
        if employee.pk not in visible_ids:
            return markers
        visible_ids = [employee.pk]

    first, last = _month_bounds(year, month)
    tz = timezone.get_current_timezone()
    range_start = timezone.make_aware(datetime.combine(first, time.min), tz)
    range_end = timezone.make_aware(
        datetime.combine(last + timedelta(days=1), time.min), tz
    )

    shifts_qs = Shift.objects.filter(
        employee_id__in=visible_ids,
        status=Shift.Status.PUBLISHED,
        starts_at__gte=range_start,
        starts_at__lt=range_end,
    ).select_related("shift_type", "employee")
    # workplace filtr úmyslně nepoužíváme — kalendář je globální přehled směn.

    shift_emp_by_day: dict[date, set[int]] = {}
    for shift in shifts_qs.order_by("starts_at"):
        if not _is_work_shift(shift):
            continue
        day = _shift_day(shift)
        if employment_for_day(shift.employee, day) is None:
            continue
        shift_emp_by_day.setdefault(day, set()).add(shift.employee_id)
        entry = markers.setdefault(
            day, {"has_shift": False, "has_plan": False, "shift_count": 0}
        )
        entry["has_shift"] = True

    for day, emp_ids in shift_emp_by_day.items():
        markers[day]["shift_count"] = len(emp_ids)

    if not shift_emp_by_day:
        return markers

    plan_rows = (
        ActivityItem.objects.filter(
            day__gte=first,
            day__lte=last,
            employee_id__in={eid for ids in shift_emp_by_day.values() for eid in ids},
        )
        .values_list("day", "employee_id")
        .distinct()
    )
    for day, emp_id in plan_rows:
        if emp_id in shift_emp_by_day.get(day, ()):
            entry = markers.setdefault(
                day, {"has_shift": False, "has_plan": False, "shift_count": 0}
            )
            entry["has_plan"] = True
            entry["has_shift"] = True
    return markers


def shift_day_in_month(day: date, year: int, month: int) -> date:
    """Stejné číslo dne v cílovém měsíci (clamp na poslední den)."""
    last = monthrange(year, month)[1]
    return date(year, month, min(day.day, last))


def build_activity_month_calendar(
    *,
    user: AbstractBaseUser,
    selected: date,
    workplace: Workplace | None,
    employee: Employee | None = None,
) -> dict[str, Any]:
    """Kontext měsíční mřížky kolem selected (Den)."""
    year, month = selected.year, selected.month
    markers = activity_month_markers(
        user, workplace, year, month, employee=employee
    )
    today = timezone.localdate()
    first, last = _month_bounds(year, month)
    lead = first.weekday()
    cells: list[dict[str, Any]] = []
    for _ in range(lead):
        cells.append({"empty": True, "css": "activity-cal-day activity-cal-day--empty"})

    for d in range(1, last.day + 1):
        day = date(year, month, d)
        m = markers.get(day, {})
        has_shift = bool(m.get("has_shift"))
        has_plan = bool(m.get("has_plan"))
        shift_count = int(m.get("shift_count") or 0)
        css = ["activity-cal-day"]
        if day == selected:
            css.append("activity-cal-day--selected")
        if day == today and day != selected:
            css.append("activity-cal-day--today")
        if has_plan:
            css.append("activity-cal-day--planned")
        elif has_shift:
            css.append("activity-cal-day--shift")
        title_parts = [day.strftime("%d.%m.%Y")]
        if shift_count:
            if shift_count == 1:
                title_parts.append("1 osoba se směnou")
            else:
                title_parts.append(f"{shift_count} osoby se směnou")
        elif has_shift:
            title_parts.append("směna")
        if has_plan:
            title_parts.append("naplánováno")
        cells.append(
            {
                "empty": False,
                "day": day,
                "iso": day.isoformat(),
                "label": str(d),
                "css": " ".join(css),
                "title": " · ".join(title_parts),
                "has_shift": has_shift,
                "has_plan": has_plan,
            }
        )

    while len(cells) % 7:
        cells.append({"empty": True, "css": "activity-cal-day activity-cal-day--empty"})

    if month == 1:
        prev_y, prev_m = year - 1, 12
    else:
        prev_y, prev_m = year, month - 1
    if month == 12:
        next_y, next_m = year + 1, 1
    else:
        next_y, next_m = year, month + 1

    return {
        "year": year,
        "month": month,
        "title": f"{_MONTH_NAMES_CS[month]} {year}",
        "weekday_headers": WEEKDAY_HEADERS,
        "cells": cells,
        "prev_day": shift_day_in_month(selected, prev_y, prev_m),
        "next_day": shift_day_in_month(selected, next_y, next_m),
        "selected": selected,
        "workplace": workplace,
        "employee": employee,
    }
