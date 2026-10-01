"""Měsíční matice plánu směn."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from django.db.models import Prefetch
from django.utils import timezone

from apps.workplaces.models import EmployeeWorkplace

from apps.shifts.fund import (
    balancing_summaries_for_month,
    employee_month_fund,
    format_hours,
    fund_summary_for_employee,
    month_day_list,
)
from apps.shifts.holidays import holidays_for_year
from apps.shifts.models import WEEKDAY_LABELS_SHORT, Shift, ShiftType
from apps.shifts.services.access import (
    can_manage_shift_plan,
    employees_visible_for_shift_plan,
)
from apps.shifts.services.mutations import MAX_SHIFTS_PER_DAY
from apps.shifts.services.workplaces import (
    employment_covers_month,
    format_workplace_assignments_label,
    nearest_future_workplace_hint,
    primary_workplace_for_month,
)


def build_month_matrix(*, user, year: int, month: int) -> dict:
    days = month_day_list(year, month)
    month_start = days[0]
    month_end = days[-1]
    holiday_map = holidays_for_year(year)
    employees = list(
        employees_visible_for_shift_plan(user).prefetch_related(
            Prefetch(
                "workplace_assignments",
                queryset=EmployeeWorkplace.objects.select_related("workplace").order_by(
                    "-valid_from"
                ),
            ),
            "employments",
        )
    )
    tz = timezone.get_current_timezone()
    range_start = timezone.make_aware(
        datetime.combine(days[0], datetime.min.time()), tz
    )
    range_end = timezone.make_aware(
        datetime.combine(days[-1] + timedelta(days=1), datetime.min.time()), tz
    )
    employee_ids = [e.pk for e in employees]
    shifts = (
        Shift.objects.filter(
            employee_id__in=employee_ids,
            starts_at__lt=range_end,
            ends_at__gt=range_start,
        )
        .exclude(status=Shift.Status.CANCELLED)
        .select_related("shift_type", "workplace", "employee")
    )
    if not can_manage_shift_plan(user):
        shifts = shifts.filter(status=Shift.Status.PUBLISHED)

    cells: dict[tuple[int, date], list[Shift]] = {}
    for shift in shifts:
        local_day = timezone.localtime(shift.starts_at, tz).date()
        if local_day.year == year and local_day.month == month:
            cells.setdefault((shift.employee_id, local_day), []).append(shift)

    mid = days[14] if len(days) > 14 else days[0]
    unassigned_key = "Bez pracoviště"
    emp_meta: dict[int, dict] = {}
    groups: dict[str, list] = {}
    for emp in employees:
        has_employment = employment_covers_month(emp, month_start, month_end)
        if not has_employment:
            continue
        primary = primary_workplace_for_month(emp, month_start, month_end)
        key = primary.name if primary else unassigned_key
        segments_label = format_workplace_assignments_label(
            emp, month_start, month_end
        )
        future_hint = ""
        if primary is None:
            future_hint = nearest_future_workplace_hint(emp, month_end)
        emp_meta[emp.pk] = {
            "workplace_name": key,
            "workplace_segments_label": segments_label,
            "workplace_future_hint": future_hint,
        }
        groups.setdefault(key, []).append(emp)

    rows = []
    for workplace_name in sorted(
        groups.keys(), key=lambda n: (n == unassigned_key, n)
    ):
        for emp in sorted(
            groups[workplace_name], key=lambda e: (e.last_name, e.first_name)
        ):
            day_cells = []
            planned = 0
            for day in days:
                day_shifts = sorted(
                    cells.get((emp.pk, day), []),
                    key=lambda s: s.starts_at,
                )
                for shift in day_shifts:
                    if shift.status == Shift.Status.PUBLISHED:
                        planned += shift.planned_net_minutes()
                codes = (
                    "+".join(s.display_code for s in day_shifts) if day_shifts else ""
                )
                day_cells.append(
                    {
                        "day": day,
                        "shifts": day_shifts,
                        "codes": codes,
                        "can_add": len(day_shifts) < MAX_SHIFTS_PER_DAY,
                        "is_weekend": day.weekday() >= 5,
                        "is_holiday": day in holiday_map,
                    }
                )
            cal_fund = employee_month_fund(
                emp,
                year,
                month,
                mid=mid,
                cells=cells,
                holiday_map=holiday_map,
            )
            fund_minutes = cal_fund["fund_minutes"]
            delta = planned - fund_minutes
            meta = emp_meta[emp.pk]
            bal_list = balancing_summaries_for_month(emp, year, month)
            rows.append(
                {
                    "employee": emp,
                    "workplace_name": meta["workplace_name"],
                    "workplace_segments_label": meta["workplace_segments_label"],
                    "workplace_future_hint": meta["workplace_future_hint"],
                    "cells": day_cells,
                    "planned_minutes": planned,
                    "planned_label": format_hours(planned),
                    "fund": cal_fund,
                    "fund_delta_minutes": delta,
                    "fund_delta_label": format_hours(abs(delta)),
                    "fund_delta_short": delta < 0,
                    "fund_delta_over": delta > 0,
                    "fund_delta_ok": delta == 0,
                    "balancing": fund_summary_for_employee(emp, mid),
                    "balancing_list": bal_list,
                }
            )

    day_headers = [
        {
            "day": day,
            "weekday_label": WEEKDAY_LABELS_SHORT[day.weekday()],
            "is_holiday": day in holiday_map,
            "holiday_name": holiday_map.get(day, ""),
            "is_weekend": day.weekday() >= 5,
        }
        for day in days
    ]
    types = list(
        ShiftType.objects.filter(is_active=True).order_by("sort_order", "code")
    )
    return {
        "year": year,
        "month": month,
        "days": days,
        "day_headers": day_headers,
        "rows": rows,
        "shift_types": types,
        "can_edit": can_manage_shift_plan(user),
    }
