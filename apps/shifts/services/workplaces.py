"""Pracoviště a pracovní vztahy v kontextu měsíčního plánu."""

from __future__ import annotations

from datetime import date, timedelta

from django.db.models import QuerySet

from apps.employees.models import Employee
from apps.workplaces.models import EmployeeWorkplace, Workplace

from apps.shifts.models import ShiftType
from apps.shifts.services.generation import resolve_assignment_for_day


def workplace_overlapping_month(
    employee: Employee, month_start: date, month_end: date
) -> Workplace | None:
    """Primární pracoviště v měsíci (zpětná kompatibilita)."""
    return primary_workplace_for_month(employee, month_start, month_end)


def _workplace_on_day_from_assignments(assignments, day: date) -> Workplace | None:
    candidates = [
        asg
        for asg in assignments
        if asg.valid_from <= day
        and (asg.valid_to is None or asg.valid_to >= day)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda a: a.valid_from).workplace


def workplace_segments_in_month(
    employee: Employee, month_start: date, month_end: date
) -> list[dict]:
    """Intervaly pracoviště v měsíci včetně mezer bez přiřazení."""
    assignments = list(employee.workplace_assignments.all())
    segments: list[dict] = []
    current_wp: Workplace | None = None
    seg_start: date | None = None
    day = month_start
    while day <= month_end:
        wp = _workplace_on_day_from_assignments(assignments, day)
        if seg_start is None:
            seg_start = day
            current_wp = wp
        elif (wp.pk if wp else None) != (current_wp.pk if current_wp else None):
            segments.append(
                {
                    "workplace": current_wp,
                    "starts_on": seg_start,
                    "ends_on": day - timedelta(days=1),
                }
            )
            seg_start = day
            current_wp = wp
        day += timedelta(days=1)
    if seg_start is not None:
        segments.append(
            {
                "workplace": current_wp,
                "starts_on": seg_start,
                "ends_on": month_end,
            }
        )
    return segments


def primary_workplace_for_month(
    employee: Employee, month_start: date, month_end: date
) -> Workplace | None:
    """Pracoviště středu měsíce, jinak nejdelší pojmenovaný segment."""
    segments = workplace_segments_in_month(employee, month_start, month_end)
    if not segments:
        return None
    mid = month_start + timedelta(days=(month_end - month_start).days // 2)
    for seg in segments:
        if seg["starts_on"] <= mid <= seg["ends_on"] and seg["workplace"]:
            return seg["workplace"]
    named = [s for s in segments if s["workplace"]]
    if not named:
        return None

    def _length(seg: dict) -> int:
        return (seg["ends_on"] - seg["starts_on"]).days + 1

    return max(named, key=_length)["workplace"]


def format_workplace_segments_label(segments: list[dict]) -> str:
    """Popisek segmentů, např. Managment (1.–15.9.) · Jih (16.–30.9.)."""
    parts: list[str] = []
    for seg in segments:
        name = seg["workplace"].name if seg["workplace"] else "Bez pracoviště"
        start = seg["starts_on"]
        end = seg["ends_on"]
        if start == end:
            date_part = f"{start.day}.{start.month}."
        else:
            date_part = f"{start.day}.–{end.day}.{end.month}."
        parts.append(f"{name} ({date_part})")
    return " · ".join(parts)


def format_workplace_assignments_label(
    employee: Employee, month_start: date, month_end: date
) -> str:
    """Platnosti pracovišť z evidence zaměstnance překrývající měsíc."""
    assignments = sorted(
        (
            asg
            for asg in employee.workplace_assignments.all()
            if asg.valid_from <= month_end
            and (asg.valid_to is None or asg.valid_to >= month_start)
        ),
        key=lambda a: a.valid_from,
    )
    parts: list[str] = []
    for asg in assignments:
        name = asg.workplace.name
        start = asg.valid_from.strftime("%d.%m.%Y")
        if asg.valid_to is None:
            parts.append(f"{name} (od {start})")
        else:
            end = asg.valid_to.strftime("%d.%m.%Y")
            parts.append(f"{name} ({start}–{end})")
    return " · ".join(parts)


def employment_covers_month(
    employee: Employee, month_start: date, month_end: date
) -> bool:
    """Aktivní pracovní vztah překrývá alespoň jeden den měsíce."""
    for emp in employee.employments.all():
        if not emp.is_active:
            continue
        if emp.started_on > month_end:
            continue
        if emp.ended_on is not None and emp.ended_on < month_start:
            continue
        return True
    return False


def filter_employees_with_employment_in_range(
    qs: QuerySet[Employee], date_from: date, date_to: date
) -> QuerySet[Employee]:
    """Aktivní zaměstnanci s aktivním Employment překrývajícím interval."""
    from django.db.models import Q

    return (
        qs.filter(
            is_active=True,
            employments__is_active=True,
            employments__started_on__lte=date_to,
        )
        .filter(
            Q(employments__ended_on__isnull=True)
            | Q(employments__ended_on__gte=date_from)
        )
        .distinct()
        .order_by("last_name", "first_name")
    )


def nearest_future_workplace_hint(employee: Employee, month_end: date) -> str:
    """Nejbližší budoucí přiřazení po konci měsíce (pro muted text)."""
    future = [
        asg
        for asg in employee.workplace_assignments.all()
        if asg.valid_from > month_end
    ]
    if not future:
        return ""
    asg = min(future, key=lambda a: a.valid_from)
    return f"{asg.workplace.name} od {asg.valid_from:%d.%m.%Y}"


def types_available_for_employee_day(employee: Employee, day: date) -> list[ShiftType]:
    """Unikátní typy ze šablony zaměstnance; jinak aktivní typy."""
    asg = resolve_assignment_for_day(employee, day)
    if asg and asg.template_id and asg.template.is_active:
        asg.template.ensure_slots()
        ids = list(
            asg.template.slots.exclude(shift_type__isnull=True)
            .values_list("shift_type_id", flat=True)
            .distinct()
        )
        if ids:
            return list(
                ShiftType.objects.filter(pk__in=ids, is_active=True).order_by(
                    "sort_order", "code"
                )
            )
    return list(
        ShiftType.objects.filter(is_active=True).order_by("sort_order", "code")
    )


def workplace_for_employee_day(employee: Employee, day: date) -> Workplace | None:
    """Pracoviště ze šablonového přiřazení, jinak překryv EmployeeWorkplace s dnem."""
    asg = resolve_assignment_for_day(employee, day)
    if asg:
        return asg.workplace
    assignments = list(
        EmployeeWorkplace.objects.filter(employee=employee)
        .select_related("workplace")
        .order_by("-valid_from")
    )
    for asg_wp in assignments:
        if asg_wp.valid_from > day:
            continue
        if asg_wp.valid_to is not None and asg_wp.valid_to < day:
            continue
        return asg_wp.workplace
    return None
