"""Šablony směn a generování plánu."""

from __future__ import annotations

from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from apps.employees.models import Employee
from apps.employees.services import employment_for_day
from apps.workplaces.models import Workplace

from apps.shifts.fund import (
    active_balancing_period_for_employee,
    month_day_list,
)
from apps.shifts.holidays import holidays_for_year
from apps.shifts.models import (
    EmployeeScheduleAssignment,
    ScheduleTemplate,
    ShiftType,
)
from apps.shifts.services.access import (
    can_manage_shift_plan,
    employees_visible_for_shift_plan,
)
from apps.shifts.services.mutations import (
    ShiftConflictError,
    assign_shift_cell,
    day_has_shift_type,
)


def monday_of_week(day: date) -> date:
    """Pondělí kalendářního týdne obsahujícího daný den (Po=0)."""
    return day - timedelta(days=day.weekday())


def resolve_assignment_for_day(
    employee: Employee, day: date
) -> EmployeeScheduleAssignment | None:
    return (
        EmployeeScheduleAssignment.objects.filter(
            employee=employee,
            is_active=True,
            valid_from__lte=day,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=day))
        .select_related("template", "workplace")
        .order_by("-valid_from")
        .first()
    )


def resolve_template_type(employee: Employee, day: date) -> ShiftType | None:
    asg = resolve_assignment_for_day(employee, day)
    if not asg or not asg.template_id or not asg.template.is_active:
        return None
    return asg.type_for_day(day)


def _generation_horizon_for_range(
    employee: Employee, date_from: date, date_to: date
) -> tuple[date, date]:
    """Omezí interval aktivním vyrovnávacím obdobím, pokud existuje."""
    mid = date_from + timedelta(days=(date_to - date_from).days // 2)
    period = active_balancing_period_for_employee(employee, mid)
    if period:
        start = max(date_from, period.starts_on)
        end = min(date_to, period.ends_on)
        if end >= start:
            return start, end
    return date_from, date_to


@transaction.atomic
def generate_shifts_from_templates(
    *,
    user,
    date_from: date,
    date_to: date,
    template: ScheduleTemplate,
    workplace: Workplace,
    cycle_anchor_date: date | None = None,
    employee_ids: list[int] | None = None,
) -> dict:
    """Vyplní dny podle zvolené šablony běhu; nepřepisuje existující typy."""
    if not can_manage_shift_plan(user):
        raise PermissionError("Nemáte oprávnění generovat plán směn.")
    if date_to < date_from:
        raise ValidationError(
            "Konec intervalu musí být stejný nebo pozdější než začátek."
        )
    if not template.is_active:
        raise ValidationError("Šablona není aktivní.")
    anchor = cycle_anchor_date or monday_of_week(date_from)
    holiday_years: set[int] = set()
    holiday_map: dict[date, str] = {}
    employees = employees_visible_for_shift_plan(user)
    if employee_ids is not None:
        employees = employees.filter(pk__in=employee_ids)
    employees = list(employees)
    created = 0
    skipped_existing = 0
    skipped_holiday = 0
    skipped_empty = 0
    skipped_no_employment = 0

    for emp in employees:
        start, end = _generation_horizon_for_range(emp, date_from, date_to)
        day = start
        while day <= end:
            if day.year not in holiday_years:
                holiday_map.update(holidays_for_year(day.year))
                holiday_years.add(day.year)
            if employment_for_day(emp, day) is None:
                skipped_no_employment += 1
                day += timedelta(days=1)
                continue
            shift_type = template.type_for_date(day, anchor)
            if not shift_type:
                skipped_empty += 1
                day += timedelta(days=1)
                continue
            if day in holiday_map and not shift_type.applies_on_holiday:
                skipped_holiday += 1
                day += timedelta(days=1)
                continue
            if day_has_shift_type(emp, day, shift_type):
                skipped_existing += 1
                day += timedelta(days=1)
                continue
            try:
                assign_shift_cell(
                    user=user,
                    employee=emp,
                    workplace=workplace,
                    day=day,
                    shift_type=shift_type,
                    publish=True,
                )
            except (ShiftConflictError, ValidationError):
                skipped_existing += 1
                day += timedelta(days=1)
                continue
            created += 1
            day += timedelta(days=1)

    return {
        "created": created,
        "skipped_existing": skipped_existing,
        "skipped_holiday": skipped_holiday,
        "skipped_empty": skipped_empty,
        "skipped_no_employment": skipped_no_employment,
    }


def generate_month_from_templates(
    *,
    user,
    year: int,
    month: int,
    template: ScheduleTemplate,
    workplace: Workplace,
    cycle_anchor_date: date | None = None,
    employee_ids: list[int] | None = None,
) -> dict:
    days = month_day_list(year, month)
    return generate_shifts_from_templates(
        user=user,
        date_from=days[0],
        date_to=days[-1],
        template=template,
        workplace=workplace,
        cycle_anchor_date=cycle_anchor_date or monday_of_week(days[0]),
        employee_ids=employee_ids,
    )
