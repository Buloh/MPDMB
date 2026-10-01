"""Zápis směn: překryvy, verze, buňka matice, publikace."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import AuditEvent
from apps.employees.models import Employee
from apps.employees.services import employment_for_day
from apps.workplaces.models import Workplace

from apps.shifts.holidays import holidays_for_year
from apps.shifts.models import Shift, ShiftType


class ShiftConflictError(ValidationError):
    """Konflikt souběžné úpravy nebo překryvu směn."""


MISSING_EMPLOYMENT_SHIFT_MSG = (
    "Nelze naplánovat směnu: chybí aktivní pracovní vztah k datu {day}. "
    "Doplňte den nástupu na kartě zaměstnance."
)

MAX_SHIFTS_PER_DAY = 12


def _require_employment_for_day(employee: Employee, day: date) -> None:
    if employment_for_day(employee, day) is None:
        raise ValidationError(
            MISSING_EMPLOYMENT_SHIFT_MSG.format(day=day.strftime("%d.%m.%Y"))
        )


def _audit(user, operation: str, shift: Shift, detail: str = "") -> None:
    AuditEvent.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        operation=operation,
        object_type="Shift",
        object_id=str(shift.pk),
        detail=detail,
    )


def find_overlapping_shifts(
    *,
    employee_id: int,
    starts_at,
    ends_at,
    exclude_pk: int | None = None,
) -> list[Shift]:
    qs = Shift.objects.filter(employee_id=employee_id).exclude(
        status=Shift.Status.CANCELLED
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    qs = qs.filter(starts_at__lt=ends_at, ends_at__gt=starts_at)
    return list(qs.select_related("workplace", "shift_type").order_by("starts_at"))


def _lock_employee_shifts(employee_id: int) -> None:
    list(
        Shift.objects.select_for_update()
        .filter(employee_id=employee_id)
        .exclude(status=Shift.Status.CANCELLED)
        .only("id")
    )


def _ensure_no_overlap(shift: Shift) -> None:
    overlaps = find_overlapping_shifts(
        employee_id=shift.employee_id,
        starts_at=shift.starts_at,
        ends_at=shift.ends_at,
        exclude_pk=shift.pk,
    )
    if overlaps:
        first = overlaps[0]
        raise ShiftConflictError(
            "Zaměstnanec má v tomto čase jinou směnu "
            f"({first.starts_at:%d.%m.%Y %H:%M}–{first.ends_at:%d.%m.%Y %H:%M}, "
            f"{first.workplace})."
        )


def apply_shift_type(shift: Shift, shift_type: ShiftType, day: date) -> Shift:
    starts, ends = shift_type.bounds_for_date(day)
    shift.shift_type = shift_type
    shift.starts_at = starts
    shift.ends_at = ends
    return shift


def shifts_on_calendar_day(employee: Employee, day: date):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, datetime.min.time()), tz)
    end = timezone.make_aware(
        datetime.combine(day + timedelta(days=1), datetime.min.time()), tz
    )
    return (
        Shift.objects.filter(employee=employee)
        .exclude(status=Shift.Status.CANCELLED)
        .filter(starts_at__lt=end, ends_at__gt=start)
    )


def day_has_shift_type(employee: Employee, day: date, shift_type: ShiftType) -> bool:
    return shifts_on_calendar_day(employee, day).filter(shift_type=shift_type).exists()


@transaction.atomic
def create_shift(*, user, shift: Shift) -> Shift:
    if shift.ends_at <= shift.starts_at:
        raise ValidationError({"ends_at": "Konec směny musí být později než začátek."})
    day = timezone.localtime(shift.starts_at).date()
    _require_employment_for_day(shift.employee, day)
    shift.status = shift.status or Shift.Status.DRAFT
    shift.version = 1
    _lock_employee_shifts(shift.employee_id)
    _ensure_no_overlap(shift)
    shift.save()
    _audit(user, "shift_create", shift, detail=shift.status)
    return shift


@transaction.atomic
def update_shift(*, user, shift: Shift, expected_version: int) -> Shift:
    locked = (
        Shift.objects.select_for_update()
        .select_related("employee", "workplace", "shift_type")
        .get(pk=shift.pk)
    )
    if locked.version != expected_version:
        raise ShiftConflictError(
            "Směnu mezitím upravil někdo jiný. Obnovte stránku a zkuste znovu."
        )
    if locked.status == Shift.Status.CANCELLED:
        raise ValidationError("Zrušenou směnu nelze upravit.")
    if shift.ends_at <= shift.starts_at:
        raise ValidationError({"ends_at": "Konec směny musí být později než začátek."})

    locked.employee = shift.employee
    locked.workplace = shift.workplace
    locked.shift_type = shift.shift_type
    locked.starts_at = shift.starts_at
    locked.ends_at = shift.ends_at
    locked.note = shift.note
    day = timezone.localtime(locked.starts_at).date()
    _require_employment_for_day(locked.employee, day)
    _lock_employee_shifts(locked.employee_id)
    _ensure_no_overlap(locked)
    locked.version = locked.version + 1
    locked.save()
    _audit(user, "shift_update", locked, detail=f"v{locked.version}")
    return locked


@transaction.atomic
def assign_shift_cell(
    *,
    user,
    employee: Employee,
    workplace: Workplace,
    day: date,
    shift_type: ShiftType,
    publish: bool = False,
) -> Shift:
    _require_employment_for_day(employee, day)
    if not shift_type.applies_on_holiday and day in holidays_for_year(day.year):
        raise ValidationError("Tento typ směny není povolen ve svátek.")
    starts, ends = shift_type.bounds_for_date(day)
    _lock_employee_shifts(employee.pk)
    day_shifts = list(
        shifts_on_calendar_day(employee, day)
        .select_for_update()
        .select_related("shift_type")
        .order_by("starts_at")
    )
    same_type = next(
        (s for s in day_shifts if s.shift_type_id == shift_type.pk),
        None,
    )
    status = Shift.Status.PUBLISHED if publish else Shift.Status.DRAFT
    if same_type:
        same_type.workplace = workplace
        same_type.shift_type = shift_type
        same_type.starts_at = starts
        same_type.ends_at = ends
        same_type.status = status
        same_type.version = same_type.version + 1
        _ensure_no_overlap(same_type)
        same_type.save()
        _audit(user, "shift_cell_update", same_type, detail=shift_type.code)
        return same_type

    if len(day_shifts) >= MAX_SHIFTS_PER_DAY:
        raise ValidationError(
            f"V jednom dni lze mít nejvýše {MAX_SHIFTS_PER_DAY} směn."
        )

    overlap = next(
        (s for s in day_shifts if s.starts_at < ends and s.ends_at > starts),
        None,
    )
    if overlap:
        raise ShiftConflictError(
            "Nová směna se časově překrývá s "
            f"{overlap.display_code} "
            f"({overlap.starts_at:%H:%M}–{overlap.ends_at:%H:%M})."
        )

    shift = Shift(
        employee=employee,
        workplace=workplace,
        shift_type=shift_type,
        starts_at=starts,
        ends_at=ends,
        status=status,
        version=1,
    )
    _ensure_no_overlap(shift)
    shift.save()
    _audit(user, "shift_cell_create", shift, detail=shift_type.code)
    return shift


@transaction.atomic
def publish_shift(*, user, shift: Shift, expected_version: int) -> Shift:
    locked = Shift.objects.select_for_update().get(pk=shift.pk)
    if locked.version != expected_version:
        raise ShiftConflictError(
            "Směnu mezitím upravil někdo jiný. Obnovte stránku a zkuste znovu."
        )
    if locked.status == Shift.Status.CANCELLED:
        raise ValidationError("Zrušenou směnu nelze publikovat.")
    locked.status = Shift.Status.PUBLISHED
    locked.version = locked.version + 1
    locked.save(update_fields=["status", "version", "updated_at"])
    _audit(user, "shift_publish", locked)
    return locked


@transaction.atomic
def cancel_shift(*, user, shift: Shift, expected_version: int) -> Shift:
    locked = Shift.objects.select_for_update().get(pk=shift.pk)
    if locked.version != expected_version:
        raise ShiftConflictError(
            "Směnu mezitím upravil někdo jiný. Obnovte stránku a zkuste znovu."
        )
    if locked.status == Shift.Status.CANCELLED:
        return locked
    locked.status = Shift.Status.CANCELLED
    locked.version = locked.version + 1
    locked.save(update_fields=["status", "version", "updated_at"])
    _audit(user, "shift_cancel", locked)
    return locked
