"""Služby evidence vozidel a kontroly přiřazení k činnostem."""

from __future__ import annotations

from datetime import date

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.dashboard import can_manage_directory
from apps.core.models import AuditEvent
from apps.employees.models import Employee, EmployeeQualification

from .models import Vehicle, VehicleDocument, normalize_plate

DRIVER_LICENSE_CODE = "ridicsky_prukaz"


class VehicleConflictError(ValidationError):
    """Konflikt přiřazení vozidla (překryv, řidičák, neaktivní)."""


def _audit(user, operation: str, obj, detail: str = "") -> None:
    AuditEvent.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        operation=operation,
        object_type=obj.__class__.__name__,
        object_id=str(obj.pk),
        detail=detail,
    )


def employee_may_drive(employee: Employee, day: date | None = None) -> bool:
    """Aktivní neprošlá kvalifikace řidičského průkazu k danému dni."""
    if day is None:
        day = timezone.localdate()
    qs = EmployeeQualification.objects.filter(
        employee=employee,
        is_active=True,
        qualification_type__code=DRIVER_LICENSE_CODE,
        qualification_type__is_active=True,
    ).filter(Q(valid_from__isnull=True) | Q(valid_from__lte=day))
    for qual in qs:
        if qual.valid_until is None or qual.valid_until >= day:
            return True
    return False


def find_overlapping_vehicle_items(
    vehicle: Vehicle,
    starts_at,
    ends_at,
    *,
    exclude_pk: int | None = None,
):
    """Činnosti se stejným vozidlem a překryvem intervalu."""
    from apps.activities.models import ActivityItem

    qs = ActivityItem.objects.filter(vehicle=vehicle).filter(
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    )
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.select_related("employee", "activity_type").order_by("starts_at")


def assert_vehicle_assignable(
    *,
    vehicle: Vehicle | None,
    employee: Employee,
    starts_at,
    ends_at,
    exclude_item_pk: int | None = None,
) -> None:
    """Validace volitelného přiřazení vozidla k činnosti."""
    if vehicle is None:
        return
    if not vehicle.is_active:
        raise VehicleConflictError(
            "Nelze přiřadit neaktivní vozidlo. Obnovte vozidlo v Technice."
        )
    day = timezone.localtime(starts_at).date()
    if not employee_may_drive(employee, day):
        raise VehicleConflictError(
            "Zaměstnanec nemá platný řidičský průkaz. "
            "Vozidlo lze přiřadit jen řidiči s aktivní kvalifikací."
        )
    overlaps = list(
        find_overlapping_vehicle_items(
            vehicle,
            starts_at,
            ends_at,
            exclude_pk=exclude_item_pk,
        )
    )
    if overlaps:
        other = overlaps[0]
        raise VehicleConflictError(
            f"Vozidlo {vehicle.plate} je už přiřazeno "
            f"({other.employee.last_name} {other.employee.first_name}, "
            f"{timezone.localtime(other.starts_at):%H:%M}–"
            f"{timezone.localtime(other.ends_at):%H:%M}). "
            "Překryv není povolen."
        )


def vehicle_document_alerts_for_user(user: AbstractBaseUser) -> list[dict]:
    """Prošlé a blížící se doklady vozidel pro modal na přehledu."""
    if not getattr(user, "is_authenticated", False):
        return []
    today = timezone.localdate()
    qs = VehicleDocument.objects.filter(
        is_active=True,
        valid_until__isnull=False,
        vehicle__is_active=True,
    ).select_related("vehicle", "vehicle__responsible", "document_type")
    if can_manage_directory(user):
        pass
    else:
        qs = qs.filter(vehicle__responsible__user=user)
    alerts: list[dict] = []
    for item in qs.order_by("valid_until", "vehicle__plate"):
        days = (item.valid_until - today).days
        warn = item.document_type.warn_days_before
        if days < 0:
            severity = "expired"
            label = "prošlá"
        elif days <= warn:
            severity = "soon"
            label = "brzy vyprší"
        else:
            continue
        alerts.append(
            {
                "document": item,
                "vehicle": item.vehicle,
                "severity": severity,
                "label": label,
                "days": days,
                "valid_until": item.valid_until,
            }
        )
    return alerts


@transaction.atomic
def save_vehicle_bundle(
    *,
    user: AbstractBaseUser,
    vehicle: Vehicle,
    document_formset,
    creating: bool,
) -> Vehicle:
    vehicle.plate = normalize_plate(vehicle.plate)
    vehicle.full_clean()
    vehicle.save()
    document_formset.instance = vehicle
    documents = document_formset.save(commit=False)
    for item in documents:
        item.vehicle = vehicle
        item.full_clean()
        item.save()
        _audit(
            user,
            "vehicle_document_save",
            item,
            detail=str(item.document_type_id),
        )
    for item in document_formset.deleted_objects:
        _audit(user, "vehicle_document_delete", item, detail=str(item.pk))
        item.delete()
    _audit(
        user,
        "vehicle_create" if creating else "vehicle_update",
        vehicle,
        detail=vehicle.plate,
    )
    return vehicle


@transaction.atomic
def archive_vehicle(*, user: AbstractBaseUser, vehicle: Vehicle) -> Vehicle:
    vehicle.is_active = False
    vehicle.save(update_fields=["is_active", "updated_at"])
    _audit(user, "vehicle_archive", vehicle, detail=vehicle.plate)
    return vehicle
