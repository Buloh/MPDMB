"""Služby plánu činností."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditEvent
from apps.employees.models import Employee
from apps.employees.services import employment_for_day
from apps.shifts.models import Shift, ShiftType
from apps.shifts.services import can_manage_shift_plan, employees_visible_for_shift_plan

from apps.technika.models import Vehicle
from apps.technika.services import (
    VehicleConflictError,
    assert_vehicle_assignable,
)

from .models import ActivityItem, ActivityLocation, ActivityType


class ActivityConflictError(ValidationError):
    """Konflikt plánu činnosti."""


def can_manage_activities(user: AbstractBaseUser) -> bool:
    return can_manage_shift_plan(user)


def can_export_activity_plan(user: AbstractBaseUser) -> bool:
    """Export PDF/Excel plánu činností — vlastní oprávnění nebo superuser."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.has_perm("activities.export_activity_plan")


def _audit(user, operation: str, object_type: str, object_id, detail: str = "") -> None:
    AuditEvent.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        operation=operation,
        object_type=object_type,
        object_id=str(object_id),
        detail=detail,
    )


def published_work_shifts_for_day(employee: Employee, day: date) -> list[Shift]:
    tz = timezone.get_current_timezone()
    range_start = timezone.make_aware(datetime.combine(day, time.min), tz)
    range_end = timezone.make_aware(
        datetime.combine(day + timedelta(days=1), time.min), tz
    )
    qs = (
        Shift.objects.filter(
            employee=employee,
            status=Shift.Status.PUBLISHED,
            starts_at__gte=range_start,
            starts_at__lt=range_end,
        )
        .select_related("shift_type", "workplace")
        .order_by("starts_at")
    )
    result = []
    for shift in qs:
        if not shift.shift_type_id:
            result.append(shift)
            continue
        st = shift.shift_type
        if st.kind == ShiftType.Kind.WORK and st.counts_as_work:
            result.append(shift)
    return result


def employees_for_activity_day(user: AbstractBaseUser, day: date):
    """Zaměstnanci s pracovním vztahem a publikovanou směnou práce v daný den."""
    visible = employees_visible_for_shift_plan(user)
    visible_ids = list(visible.values_list("pk", flat=True))
    if not visible_ids:
        return Employee.objects.none()

    tz = timezone.get_current_timezone()
    range_start = timezone.make_aware(datetime.combine(day, time.min), tz)
    range_end = timezone.make_aware(
        datetime.combine(day + timedelta(days=1), time.min), tz
    )
    day_shifts = (
        Shift.objects.filter(
            employee_id__in=visible_ids,
            status=Shift.Status.PUBLISHED,
            starts_at__gte=range_start,
            starts_at__lt=range_end,
        )
        .select_related("shift_type", "employee")
        .order_by("starts_at")
    )
    eligible: set[int] = set()
    for shift in day_shifts:
        if shift.employee_id in eligible:
            continue
        if shift.shift_type_id:
            st = shift.shift_type
            if not (st.kind == ShiftType.Kind.WORK and st.counts_as_work):
                continue
        if employment_for_day(shift.employee, day) is None:
            continue
        eligible.add(shift.employee_id)

    return visible.filter(pk__in=eligible).order_by("last_name", "first_name")


def can_plan_activity_for_day(
    user: AbstractBaseUser, employee: Employee, day: date
) -> bool:
    return employees_for_activity_day(user, day).filter(pk=employee.pk).exists()


def items_for_day(employee: Employee, day: date) -> list[ActivityItem]:
    return list(
        ActivityItem.objects.filter(employee=employee, day=day)
        .select_related(
            "location",
            "location__parent",
            "activity_type",
            "shift",
            "shift__shift_type",
            "vehicle",
        )
        .order_by("sort_order", "starts_at", "id")
    )


def hour_items_for_day(employee: Employee, day: date) -> list[ActivityItem]:
    return [it for it in items_for_day(employee, day) if not it.all_day]


def day_tasks_for_day(employee: Employee, day: date) -> list[ActivityItem]:
    return [it for it in items_for_day(employee, day) if it.all_day]


def _ensure_within_shift(shift: Shift, starts_at, ends_at) -> None:
    if starts_at < shift.starts_at or ends_at > shift.ends_at:
        raise ActivityConflictError(
            "Čas činnosti musí být uvnitř publikované směny "
            f"({timezone.localtime(shift.starts_at):%H:%M}–"
            f"{timezone.localtime(shift.ends_at):%H:%M})."
        )


@transaction.atomic
def create_activity_item(
    *,
    user: AbstractBaseUser,
    employee: Employee,
    shift: Shift,
    location: ActivityLocation | None,
    activity_type: ActivityType,
    starts_at,
    ends_at,
    note: str = "",
    sort_order: int = 100,
    all_day: bool = False,
    vehicle: Vehicle | None = None,
) -> ActivityItem:
    if shift.employee_id != employee.pk:
        raise ActivityConflictError("Směna nepatří vybranému zaměstnanci.")
    if shift.status != Shift.Status.PUBLISHED:
        raise ActivityConflictError("Činnost lze plánovat jen u publikované směny.")
    day = timezone.localtime(shift.starts_at).date()
    # Denní úkol pokrývá rozsah směn dne; nemusí ležet v jedné směně.
    if not all_day:
        _ensure_within_shift(shift, starts_at, ends_at)
    try:
        assert_vehicle_assignable(
            vehicle=vehicle,
            employee=employee,
            starts_at=starts_at,
            ends_at=ends_at,
        )
    except VehicleConflictError as exc:
        raise ActivityConflictError(exc.messages) from exc
    item = ActivityItem(
        employee=employee,
        day=day,
        shift=shift,
        location=location,
        activity_type=activity_type,
        vehicle=vehicle,
        starts_at=starts_at,
        ends_at=ends_at,
        note=(note or "").strip(),
        sort_order=sort_order,
        all_day=bool(all_day),
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    item.full_clean()
    item.save()
    loc_code = location.code if location else "—"
    plate = vehicle.plate if vehicle else "—"
    _audit(
        user,
        "activity.create",
        "ActivityItem",
        item.pk,
        f"{loc_code}; {plate}; {starts_at}–{ends_at}; all_day={item.all_day}",
    )
    return item


@transaction.atomic
def update_activity_item(
    *,
    user: AbstractBaseUser,
    item: ActivityItem,
    location: ActivityLocation | None,
    activity_type: ActivityType,
    starts_at,
    ends_at,
    note: str = "",
    sort_order: int | None = None,
    expected_version: int | None = None,
    shift: Shift | None = None,
    vehicle: Vehicle | None = None,
) -> ActivityItem:
    if expected_version is not None and item.version != expected_version:
        raise ActivityConflictError(
            "Záznam byl mezitím změněn. Obnovte stránku."
        )
    target_shift = shift or item.shift
    if target_shift.employee_id != item.employee_id:
        raise ActivityConflictError("Směna nepatří vybranému zaměstnanci.")
    if target_shift.status != Shift.Status.PUBLISHED:
        raise ActivityConflictError("Činnost lze plánovat jen u publikované směny.")
    if not item.all_day:
        _ensure_within_shift(target_shift, starts_at, ends_at)
    try:
        assert_vehicle_assignable(
            vehicle=vehicle,
            employee=item.employee,
            starts_at=starts_at,
            ends_at=ends_at,
            exclude_item_pk=item.pk,
        )
    except VehicleConflictError as exc:
        raise ActivityConflictError(exc.messages) from exc
    item.shift = target_shift
    item.day = timezone.localtime(target_shift.starts_at).date()
    item.location = location
    item.activity_type = activity_type
    item.vehicle = vehicle
    item.starts_at = starts_at
    item.ends_at = ends_at
    item.note = (note or "").strip()
    if sort_order is not None:
        item.sort_order = sort_order
    item.version += 1
    item.full_clean()
    item.save()
    _audit(user, "activity.update", "ActivityItem", item.pk, "")
    return item


@transaction.atomic
def delete_activity_item(*, user: AbstractBaseUser, item: ActivityItem) -> None:
    pk = item.pk
    item.delete()
    _audit(user, "activity.delete", "ActivityItem", pk, "")


@transaction.atomic
def save_activity_location(
    *,
    user: AbstractBaseUser,
    location: ActivityLocation,
    create: bool,
) -> ActivityLocation:
    location.full_clean()
    location.save()
    _audit(
        user,
        "activity_location.create" if create else "activity_location.update",
        "ActivityLocation",
        location.pk,
        location.code,
    )
    return location


def locations_geojson_collection(*, exclude_id: int | None = None) -> dict:
    features = []
    qs = (
        ActivityLocation.objects.filter(is_active=True)
        .select_related("parent", "workplace")
        .order_by("sort_order", "code")
    )
    if exclude_id is not None:
        qs = qs.exclude(pk=exclude_id)
    for loc in qs:
        try:
            geom = loc.geometry_dict()
        except (ValueError, TypeError):
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": loc.pk,
                    "code": loc.code,
                    "name": loc.name,
                    "label": loc.hierarchy_label(),
                    "level": "sub" if loc.parent_id else "main",
                    "color": loc.color or "#166999",
                    "description": loc.description or "",
                    "workplace": (
                        str(loc.workplace) if loc.workplace_id else ""
                    ),
                    "parent_code": loc.parent.code if loc.parent_id else "",
                    "edit_url": reverse(
                        "activity_location_edit", args=[loc.pk]
                    ),
                },
                "geometry": geom,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def resolve_map_city(city_code: str | None = None):
    """Vrátí aktivní MapCity podle kódu, jinak výchozí, jinak první aktivní."""
    from .models import MapCity

    qs = MapCity.objects.filter(is_active=True)
    if city_code:
        city = qs.filter(code=city_code).first()
        if city:
            return city
    city = qs.filter(is_default=True).first()
    if city:
        return city
    return qs.order_by("sort_order", "name").first()


def map_cities_active():
    from .models import MapCity

    return list(
        MapCity.objects.filter(is_active=True).order_by("sort_order", "name")
    )


def locations_grouped_for_list() -> list[ActivityLocation]:
    """Hlavní lokace a hned za nimi jejich podlokace."""
    mains = list(
        ActivityLocation.objects.filter(parent__isnull=True)
        .select_related("workplace")
        .prefetch_related("children__workplace")
        .order_by("sort_order", "code")
    )
    result: list[ActivityLocation] = []
    for main in mains:
        result.append(main)
        children = sorted(
            main.children.all(),
            key=lambda c: (c.sort_order, c.code),
        )
        result.extend(children)
    orphans = (
        ActivityLocation.objects.filter(parent__isnull=False)
        .exclude(parent__in=[m.pk for m in mains])
        .select_related("parent", "workplace")
        .order_by("sort_order", "code")
    )
    result.extend(list(orphans))
    return result
