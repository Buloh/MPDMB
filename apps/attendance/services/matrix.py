"""Měsíční matice a detail dne docházky."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Prefetch
from django.utils import timezone

from apps.employees.models import Employee
from apps.employees.services import employment_for_day
from apps.shifts.fund import format_hours, month_day_list
from apps.shifts.holidays import holidays_for_year
from apps.shifts.models import WEEKDAY_LABELS_SHORT, Shift
from apps.shifts.services import (
    can_manage_shift_plan,
    employment_covers_month,
    format_workplace_assignments_label,
    nearest_future_workplace_hint,
    primary_workplace_for_month,
)
from apps.workplaces.models import EmployeeWorkplace

from ..models import Absence, AbsenceType, MealAllowanceSettings, WorkInterval
from .common import (
    _proposed_break_minutes,
    can_access_employee_attendance,
    can_manage_attendance,
    employees_visible_for_attendance,
    is_attendance_matrix_shift,
    is_published_leave_shift,
    is_published_work_shift,
    shift_local_day,
)


def meal_vouchers_for_day(worked_minutes: int, settings: MealAllowanceSettings) -> int:
    """Počet stravenek za den (0–2) podle čisté potvrzené práce a prahů."""
    if not settings.is_active:
        return 0
    if worked_minutes < settings.min_worked_minutes:
        return 0
    second = settings.second_worked_minutes
    if second is not None and worked_minutes >= second:
        return 2
    return 1


@dataclass
class DayAttendanceCell:
    day: date
    weekday_label: str
    is_weekend: bool
    is_holiday: bool
    holiday_name: str
    shifts: list[Shift]
    work_intervals: list[WorkInterval]
    absences: list[Absence]
    status: str  # empty | unresolved | work | absence
    status_label: str
    planned_minutes: int
    worked_minutes: int
    missed_minutes: int
    menu_shift_id: int | None = None
    plan_codes: str = ""
    plan_title: str = ""
    missing_employment: bool = False


@dataclass
class EmployeeAttendanceRow:
    employee: Employee
    cells: list[DayAttendanceCell]
    planned_minutes: int
    worked_minutes: int
    missed_minutes: int
    unresolved_count: int
    absence_by_code: dict[str, int]
    planned_label: str
    worked_label: str
    missed_label: str
    workplace_name: str = ""
    workplace_segments_label: str = ""
    workplace_future_hint: str = ""
    has_missing_employment: bool = False
    meal_vouchers: int = 0


def month_attendance_matrix(
    *, user: AbstractBaseUser, year: int, month: int
) -> dict:
    days = month_day_list(year, month)
    holidays = holidays_for_year(year)
    if not days:
        return {
            "year": year,
            "month": month,
            "day_headers": [],
            "rows": [],
            "can_edit": can_manage_attendance(user),
            "summary": {
                "planned_minutes": 0,
                "worked_minutes": 0,
                "missed_minutes": 0,
                "unresolved_count": 0,
                "meal_vouchers": 0,
            },
            "meal_threshold_minutes": None,
            "meal_second_threshold_minutes": None,
            "absence_types": list(
                AbsenceType.objects.filter(is_active=True).order_by("sort_order")
            ),
        }

    month_start, month_end = days[0], days[-1]
    tz = timezone.get_current_timezone()
    range_start = timezone.make_aware(datetime.combine(days[0], time.min), tz)
    range_end = timezone.make_aware(
        datetime.combine(days[-1] + timedelta(days=1), time.min), tz
    )

    visible = list(
        employees_visible_for_attendance(user).prefetch_related(
            "employments",
            Prefetch(
                "workplace_assignments",
                queryset=EmployeeWorkplace.objects.select_related("workplace").order_by(
                    "-valid_from"
                ),
            ),
        )
    )
    visible_ids = [e.pk for e in visible]
    month_shifts = list(
        Shift.objects.filter(
            employee_id__in=visible_ids,
            status=Shift.Status.PUBLISHED,
            starts_at__gte=range_start,
            starts_at__lt=range_end,
        )
        .select_related("shift_type", "workplace")
        .order_by("starts_at")
    )
    work_shifts_all = [s for s in month_shifts if is_attendance_matrix_shift(s)]
    ids_with_plan = {
        s.employee_id for s in month_shifts if is_published_work_shift(s)
    }
    employees = [
        emp
        for emp in visible
        if employment_covers_month(emp, month_start, month_end)
        or emp.pk in ids_with_plan
    ]
    emp_ids = {e.pk for e in employees}
    work_shifts = [s for s in work_shifts_all if s.employee_id in emp_ids]
    shift_ids = [s.pk for s in work_shifts]
    intervals = list(
        WorkInterval.objects.filter(shift_id__in=shift_ids).select_related("shift")
    )
    absences = list(
        Absence.objects.filter(shift_id__in=shift_ids).select_related(
            "absence_type", "shift"
        )
    )
    intervals_by_shift: dict[int, list[WorkInterval]] = {}
    for wi in intervals:
        intervals_by_shift.setdefault(wi.shift_id, []).append(wi)
    absences_by_shift: dict[int, list[Absence]] = {}
    for ab in absences:
        absences_by_shift.setdefault(ab.shift_id, []).append(ab)
    shifts_by_emp_day: dict[tuple[int, date], list[Shift]] = {}
    for s in work_shifts:
        key = (s.employee_id, shift_local_day(s))
        shifts_by_emp_day.setdefault(key, []).append(s)

    # Náhled dlouhodobého plánu (= měsíční plán směn, bez zrušených).
    plan_qs = (
        Shift.objects.filter(
            employee_id__in=emp_ids,
            starts_at__lt=range_end,
            ends_at__gt=range_start,
        )
        .exclude(status=Shift.Status.CANCELLED)
        .select_related("shift_type", "workplace")
        .order_by("starts_at")
    )
    if not can_manage_shift_plan(user):
        plan_qs = plan_qs.filter(status=Shift.Status.PUBLISHED)
    plan_by_emp_day: dict[tuple[int, date], list[Shift]] = {}
    for s in plan_qs:
        local_day = timezone.localtime(s.starts_at, tz).date()
        if local_day.year == year and local_day.month == month:
            plan_by_emp_day.setdefault((s.employee_id, local_day), []).append(s)

    adhoc_by_emp_day: dict[tuple[int, date], list[WorkInterval]] = {}
    if emp_ids:
        for wi in (
            WorkInterval.objects.filter(
                employment__employee_id__in=emp_ids,
                shift__isnull=True,
                status=WorkInterval.Status.CONFIRMED,
                starts_at__gte=range_start,
                starts_at__lt=range_end,
            )
            .select_related("employment", "workplace")
            .order_by("starts_at")
        ):
            key = (
                wi.employment.employee_id,
                timezone.localtime(wi.starts_at).date(),
            )
            adhoc_by_emp_day.setdefault(key, []).append(wi)

    day_headers = []
    for d in days:
        day_headers.append(
            {
                "day": d,
                "weekday_label": WEEKDAY_LABELS_SHORT[d.weekday()],
                "is_weekend": d.weekday() >= 5,
                "is_holiday": d in holidays,
                "holiday_name": holidays.get(d, ""),
            }
        )

    rows: list[EmployeeAttendanceRow] = []
    sum_planned = sum_worked = sum_missed = sum_unresolved = sum_meals = 0
    absence_types = list(
        AbsenceType.objects.filter(is_active=True).order_by("sort_order")
    )
    meal_settings = MealAllowanceSettings.load()
    meal_threshold = (
        meal_settings.min_worked_minutes if meal_settings.is_active else None
    )
    meal_second_threshold = (
        meal_settings.second_worked_minutes if meal_settings.is_active else None
    )

    for emp in employees:
        cells: list[DayAttendanceCell] = []
        row_planned = row_worked = row_missed = row_unresolved = 0
        row_meals = 0
        absence_by_code = {t.code: 0 for t in absence_types}
        for d in days:
            day_shifts = shifts_by_emp_day.get((emp.pk, d), [])
            day_wi: list[WorkInterval] = []
            day_ab: list[Absence] = []
            planned = 0
            worked = 0
            missed = 0
            status = "empty"
            status_label = "—"
            has_unresolved_shift = False
            menu_shift_id: int | None = None
            for s in day_shifts:
                if is_published_work_shift(s):
                    planned += s.planned_net_minutes()
                wis = intervals_by_shift.get(s.pk, [])
                abs_list = absences_by_shift.get(s.pk, [])
                day_wi.extend(wis)
                day_ab.extend(abs_list)
                confirmed = [
                    w for w in wis if w.status == WorkInterval.Status.CONFIRMED
                ]
                if abs_list:
                    for ab in abs_list:
                        missed += ab.planned_missed_minutes
                        absence_by_code[ab.absence_type.code] = (
                            absence_by_code.get(ab.absence_type.code, 0)
                            + ab.planned_missed_minutes
                        )
                elif confirmed:
                    for w in confirmed:
                        worked += w.net_minutes()
                elif is_published_work_shift(s):
                    has_unresolved_shift = True
                    if menu_shift_id is None:
                        menu_shift_id = s.pk
                elif is_published_leave_shift(s):
                    # schválená D bez absence — stále nevyřešeno, ale bez menu práce
                    has_unresolved_shift = True

            adhoc = adhoc_by_emp_day.get((emp.pk, d), [])
            for w in adhoc:
                day_wi.append(w)
                worked += w.net_minutes()

            if day_shifts:
                if day_ab and not any(
                    w.status == WorkInterval.Status.CONFIRMED for w in day_wi
                ):
                    names = ", ".join(
                        sorted({a.absence_type.name for a in day_ab})
                    )
                    status = "absence"
                    status_label = names
                    menu_shift_id = None
                elif any(
                    w.status == WorkInterval.Status.CONFIRMED for w in day_wi
                ) and not day_ab:
                    status = "work"
                    status_label = "Práce"
                    menu_shift_id = None
                elif any(
                    w.status == WorkInterval.Status.CONFIRMED for w in day_wi
                ) and day_ab:
                    status = "conflict"
                    status_label = "Konflikt"
                    menu_shift_id = None
                else:
                    status = "unresolved"
                    status_label = "Nevyřešeno"
                if has_unresolved_shift:
                    row_unresolved += 1
            elif adhoc:
                status = "work"
                status_label = "Práce"

            plan_shifts = plan_by_emp_day.get((emp.pk, d), [])
            plan_codes = "+".join(s.display_code for s in plan_shifts) if plan_shifts else ""
            plan_parts = []
            for s in plan_shifts:
                local_start = timezone.localtime(s.starts_at)
                local_end = timezone.localtime(s.ends_at)
                part = (
                    f"{s.display_code} {local_start.strftime('%H:%M')}–"
                    f"{local_end.strftime('%H:%M')} ({s.get_status_display()})"
                )
                if s.shift_type_id and s.shift_type.kind == "leave":
                    portion = s._leave_portion()
                    if portion == "am":
                        part += " · půldenní dovolená dopoledne"
                    elif portion == "pm":
                        part += " · půldenní dovolená odpoledne"
                    else:
                        part += " · dovolená"
                plan_parts.append(part)
            plan_title = "; ".join(plan_parts)

            missing_employment = bool(
                day_shifts and employment_for_day(emp, d) is None
            )

            cells.append(
                DayAttendanceCell(
                    day=d,
                    weekday_label=WEEKDAY_LABELS_SHORT[d.weekday()],
                    is_weekend=d.weekday() >= 5,
                    is_holiday=d in holidays,
                    holiday_name=holidays.get(d, ""),
                    shifts=day_shifts,
                    work_intervals=day_wi,
                    absences=day_ab,
                    status=status,
                    status_label=status_label,
                    planned_minutes=planned,
                    worked_minutes=worked,
                    missed_minutes=missed,
                    menu_shift_id=menu_shift_id if status == "unresolved" else None,
                    plan_codes=plan_codes,
                    plan_title=plan_title,
                    missing_employment=missing_employment,
                )
            )
            row_planned += planned
            row_worked += worked
            row_missed += missed
            if meal_threshold is not None:
                row_meals += meal_vouchers_for_day(worked, meal_settings)

        primary = primary_workplace_for_month(emp, month_start, month_end)
        unassigned_key = "Bez pracoviště"
        wp_name = primary.name if primary else unassigned_key
        segments_label = format_workplace_assignments_label(
            emp, month_start, month_end
        )
        future_hint = ""
        if primary is None:
            future_hint = nearest_future_workplace_hint(emp, month_end)

        rows.append(
            EmployeeAttendanceRow(
                employee=emp,
                cells=cells,
                planned_minutes=row_planned,
                worked_minutes=row_worked,
                missed_minutes=row_missed,
                unresolved_count=row_unresolved,
                absence_by_code=absence_by_code,
                planned_label=format_hours(row_planned),
                worked_label=format_hours(row_worked),
                missed_label=format_hours(row_missed),
                workplace_name=wp_name,
                workplace_segments_label=segments_label,
                workplace_future_hint=future_hint,
                has_missing_employment=any(c.missing_employment for c in cells),
                meal_vouchers=row_meals,
            )
        )
        sum_planned += row_planned
        sum_worked += row_worked
        sum_missed += row_missed
        sum_unresolved += row_unresolved
        sum_meals += row_meals

    unassigned_key = "Bez pracoviště"
    rows.sort(
        key=lambda r: (
            r.workplace_name == unassigned_key,
            r.workplace_name,
            r.employee.last_name,
            r.employee.first_name,
        )
    )

    return {
        "year": year,
        "month": month,
        "day_headers": day_headers,
        "rows": rows,
        "can_edit": can_manage_attendance(user)
        or bool(employees),  # zaměstnanec může potvrdit sebe
        "can_manage": can_manage_attendance(user),
        "summary": {
            "planned_minutes": sum_planned,
            "worked_minutes": sum_worked,
            "missed_minutes": sum_missed,
            "unresolved_count": sum_unresolved,
            "meal_vouchers": sum_meals,
            "planned_label": format_hours(sum_planned),
            "worked_label": format_hours(sum_worked),
            "missed_label": format_hours(sum_missed),
        },
        "meal_threshold_minutes": meal_threshold,
        "meal_second_threshold_minutes": meal_second_threshold,
        "absence_types": absence_types,
        "format_hours": format_hours,
    }


def attendance_day_detail(
    *, user: AbstractBaseUser, employee: Employee, day: date
) -> dict:
    if not can_access_employee_attendance(user, employee):
        raise PermissionError("Nemáte oprávnění k docházce tohoto zaměstnance.")
    shifts = [
        s
        for s in Shift.objects.filter(
            employee=employee,
            status=Shift.Status.PUBLISHED,
        )
        .select_related("shift_type", "workplace")
        .order_by("starts_at")
        if shift_local_day(s) == day and is_published_work_shift(s)
    ]
    shift_ids = [s.pk for s in shifts]
    intervals = {
        wi.shift_id: wi
        for wi in WorkInterval.objects.filter(shift_id__in=shift_ids)
    }
    absences = {
        ab.shift_id: ab
        for ab in Absence.objects.filter(shift_id__in=shift_ids).select_related(
            "absence_type"
        )
    }
    items = []
    for s in shifts:
        wi = intervals.get(s.pk)
        ab = absences.get(s.pk)
        if ab:
            state = "absence"
        elif wi and wi.status == WorkInterval.Status.CONFIRMED:
            state = "work"
        else:
            state = "unresolved"
        items.append(
            {
                "shift": s,
                "work_interval": wi,
                "absence": ab,
                "state": state,
                "proposed_break": _proposed_break_minutes(s),
                "planned_net": s.planned_net_minutes(),
                "planned_label": format_hours(s.planned_net_minutes()),
                "worked_label": format_hours(wi.net_minutes()) if wi else "0:00",
                "missed_label": format_hours(ab.planned_missed_minutes)
                if ab
                else "0:00",
            }
        )
    tz = timezone.get_current_timezone()
    day_start = timezone.make_aware(datetime.combine(day, time.min), tz)
    day_end = timezone.make_aware(
        datetime.combine(day + timedelta(days=1), time.min), tz
    )
    ad_hoc = list(
        WorkInterval.objects.filter(
            employment__employee=employee,
            shift__isnull=True,
            starts_at__gte=day_start,
            starts_at__lt=day_end,
        )
        .select_related("workplace")
        .order_by("starts_at")
    )
    return {
        "employee": employee,
        "day": day,
        "items": items,
        "ad_hoc_intervals": ad_hoc,
        "absence_types": list(
            AbsenceType.objects.filter(is_active=True).order_by("sort_order")
        ),
        "can_edit": can_access_employee_attendance(user, employee),
        "can_manage": can_manage_attendance(user),
        "holiday_name": holidays_for_year(day.year).get(day, ""),
    }
