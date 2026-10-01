"""Sestava dat pro export plánu činností (HTML/PDF tisk i Excel)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from apps.employees.models import Employee
from apps.workplaces.models import Workplace

from .models import ActivityItem, ActivityLocation
from .schedule import employees_for_workplace_day
from .services import (
    day_tasks_for_day,
    hour_items_for_day,
    published_work_shifts_for_day,
)


@dataclass
class ExportPersonDay:
    employee: Employee
    shifts: list
    hour_items: list[ActivityItem]
    day_tasks: list[ActivityItem]


@dataclass
class ActivityExportPack:
    day: date
    workplace: Workplace | None
    persons: list[ExportPersonDay]
    locations: list[ActivityLocation]
    exported_at: object
    scope_label: str


def build_activity_export_pack(
    *,
    user: AbstractBaseUser,
    day: date,
    employee: Employee | None = None,
    workplace: Workplace | None = None,
) -> ActivityExportPack:
    persons: list[ExportPersonDay] = []
    if employee is not None:
        persons.append(
            ExportPersonDay(
                employee=employee,
                shifts=published_work_shifts_for_day(employee, day),
                hour_items=hour_items_for_day(employee, day),
                day_tasks=day_tasks_for_day(employee, day),
            )
        )
        scope_label = f"{employee.last_name} {employee.first_name}"
    elif workplace is not None:
        for emp in employees_for_workplace_day(user, day, workplace):
            persons.append(
                ExportPersonDay(
                    employee=emp,
                    shifts=[
                        s
                        for s in published_work_shifts_for_day(emp, day)
                        if s.workplace_id == workplace.pk
                    ],
                    hour_items=hour_items_for_day(emp, day),
                    day_tasks=day_tasks_for_day(emp, day),
                )
            )
        scope_label = str(workplace)
    else:
        scope_label = "—"

    loc_ids: set[int] = set()
    for p in persons:
        for it in p.hour_items + p.day_tasks:
            if it.location_id:
                loc_ids.add(it.location_id)
    locations = list(
        ActivityLocation.objects.filter(pk__in=loc_ids)
        .select_related("parent")
        .order_by("sort_order", "code")
    )
    return ActivityExportPack(
        day=day,
        workplace=workplace,
        persons=persons,
        locations=locations,
        exported_at=timezone.localtime(),
        scope_label=scope_label,
    )
