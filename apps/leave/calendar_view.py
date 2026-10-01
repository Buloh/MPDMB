"""Roční kalendář dovolené (12 pásů měsíců)."""

from __future__ import annotations

from calendar import monthrange
from datetime import date

from apps.employees.models import Employee, Employment
from apps.employees.services import employment_for_day
from apps.shifts.holidays import holidays_for_year
from apps.workplaces.models import EmployeeWorkplace

from .models import LeavePlan, LeavePlanDay

MONTH_NAMES_CS = (
    "",
    "Leden",
    "Únor",
    "Březen",
    "Duben",
    "Květen",
    "Červen",
    "Červenec",
    "Srpen",
    "Září",
    "Říjen",
    "Listopad",
    "Prosinec",
)

WEEKDAY_HEADERS = ("Po", "Út", "St", "Čt", "Pá", "So", "Ne")


def leave_cells_for_employment(employment: Employment, year: int) -> dict[date, dict]:
    """Mapa den → stav dovolené pro kalendář."""
    cells: dict[date, dict] = {}
    plans = (
        LeavePlan.objects.filter(employment=employment, year=year)
        .exclude(status=LeavePlan.Status.CANCELLED)
        .prefetch_related("days")
    )
    for plan in plans:
        if plan.status == LeavePlan.Status.DRAFT:
            cur = plan.starts_on
            while cur <= plan.ends_on:
                if cur.weekday() < 5 and cur.year == year:
                    label = "Návrh"
                    if plan.portion == LeavePlanDay.Portion.AM:
                        label = "Návrh dopoledne"
                    elif plan.portion == LeavePlanDay.Portion.PM:
                        label = "Návrh odpoledne"
                    cells[cur] = {
                        "status": "draft",
                        "portion": plan.portion,
                        "plan_id": plan.pk,
                        "title": f"{label} {plan.starts_on:%d.%m.}–{plan.ends_on:%d.%m.}",
                        "css": "leave-day--draft",
                        "mark": "N",
                    }
                cur = date.fromordinal(cur.toordinal() + 1)
            continue
        for day_row in plan.days.all():
            portion = day_row.portion
            if portion == LeavePlanDay.Portion.AM:
                mark = "D/"
                title = "Půldenní dovolená dopoledne"
            elif portion == LeavePlanDay.Portion.PM:
                mark = "D\\"
                title = "Půldenní dovolená odpoledne"
            else:
                mark = "D"
                title = "Dovolená"
            cells[day_row.day] = {
                "status": "approved",
                "portion": portion,
                "plan_id": plan.pk,
                "title": title,
                "css": "leave-day--approved",
                "mark": mark,
            }
    return cells


def _day_cell(d: date, leave_cells: dict[date, dict], holidays: dict[date, str]) -> dict:
    leave = leave_cells.get(d)
    is_weekend = d.weekday() >= 5
    is_holiday = d in holidays
    css = ["leave-day"]
    title_parts: list[str] = [f"{d:%d.%m.%Y}"]
    mark = str(d.day)
    if is_weekend:
        css.append("leave-day--weekend")
    if is_holiday:
        css.append("leave-day--holiday")
        title_parts.append(holidays[d])
    if leave:
        css.append(leave["css"])
        title_parts.append(leave["title"])
        mark = leave["mark"]
    return {
        "empty": False,
        "day": d,
        "iso": d.isoformat(),
        "label": str(d.day),
        "css": " ".join(css),
        "title": " · ".join(title_parts),
        "mark": mark,
        "clickable": d.weekday() < 5,
        "has_leave": bool(leave),
    }


def build_year_months(
    *,
    year: int,
    leave_cells: dict[date, dict],
) -> list[dict]:
    """12 měsíců — každý s plochým seznamem dnů 1…N (vodorovný pás)."""
    holidays = holidays_for_year(year)
    months: list[dict] = []
    for month in range(1, 13):
        _, last_day = monthrange(year, month)
        days = [
            _day_cell(date(year, month, day_num), leave_cells, holidays)
            for day_num in range(1, last_day + 1)
        ]
        months.append(
            {
                "month": month,
                "name": MONTH_NAMES_CS[month],
                "days": days,
            }
        )
    return months


def year_calendar_for_employment(employment: Employment, year: int) -> list[dict]:
    return build_year_months(
        year=year,
        leave_cells=leave_cells_for_employment(employment, year),
    )


def employees_for_workplace_year(workplace, year: int) -> list:
    """Zaměstnanci s přiřazením k pracovišti překrývajícím daný rok."""
    from django.db.models import Q

    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    emp_ids = (
        EmployeeWorkplace.objects.filter(workplace=workplace)
        .filter(valid_from__lte=year_end)
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=year_start))
        .values_list("employee_id", flat=True)
        .distinct()
    )
    employees = list(
        Employee.objects.filter(pk__in=emp_ids, is_active=True).order_by(
            "last_name", "first_name"
        )
    )
    rows = []
    for emp in employees:
        employment = employment_for_day(emp, date(year, 7, 1)) or (
            emp.employments.filter(is_active=True).order_by("-started_on").first()
        )
        if employment is None:
            continue
        if employment.relation_type != Employment.RelationType.EMPLOYMENT:
            continue
        rows.append(
            {
                "employee": emp,
                "employment": employment,
                "calendar_months": year_calendar_for_employment(employment, year),
            }
        )
    return rows
