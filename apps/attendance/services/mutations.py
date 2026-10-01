"""Zápis docházky: potvrzení, absence, ad-hoc práce."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from apps.employees.models import Employee
from apps.employees.services import employment_for_day
from apps.shifts.holidays import holidays_for_year
from apps.shifts.models import Shift
from apps.workplaces.models import Workplace

from ..models import Absence, AbsenceType, WorkInterval
from .common import (
    MISSING_EMPLOYMENT_ADHOC_MSG,
    MISSING_EMPLOYMENT_CODE,
    MISSING_EMPLOYMENT_MSG,
    AttendanceConflictError,
    _audit,
    _proposed_break_minutes,
    can_manage_attendance,
    is_published_work_shift,
    published_work_shifts_for_month,
    shift_local_day,
)


@transaction.atomic
def create_ad_hoc_work_interval(
    *,
    user: AbstractBaseUser,
    employee: Employee,
    workplace: Workplace,
    starts_at,
    ends_at,
    break_minutes: int = 0,
    note: str = "",
) -> WorkInterval:
    """Potvrzená práce bez vazby na publikovanou směnu (např. So/Ne)."""
    if not can_manage_attendance(user):
        raise AttendanceConflictError(
            "Ad-hoc práci může zapsat jen vedoucí nebo administrátor."
        )
    if ends_at <= starts_at:
        raise AttendanceConflictError(
            {"ends_at": "Konec musí být později než začátek."}
        )
    day = timezone.localtime(starts_at).date()
    end_day = timezone.localtime(ends_at).date()
    if end_day not in (day, day + timedelta(days=1)):
        raise AttendanceConflictError(
            "Ad-hoc interval smí končit jen ve stejném dni nebo následující den (přes půlnoc)."
        )
    employment = employment_for_day(employee, day)
    if employment is None:
        raise AttendanceConflictError(
            MISSING_EMPLOYMENT_ADHOC_MSG,
            code=MISSING_EMPLOYMENT_CODE,
        )
    pause = max(0, int(break_minutes or 0))
    interval = WorkInterval(
        employment=employment,
        workplace=workplace,
        shift=None,
        starts_at=starts_at,
        ends_at=ends_at,
        break_minutes=pause,
        status=WorkInterval.Status.CONFIRMED,
        version=1,
        confirmed_by=user if getattr(user, "is_authenticated", False) else None,
        confirmed_at=timezone.now(),
        note=(note or "")[:255],
    )
    interval.full_clean()
    interval.save()
    _audit(
        user,
        "attendance.ad_hoc_work",
        "WorkInterval",
        interval.pk,
        f"employee={employee.pk}; {starts_at}–{ends_at}; pauza={pause}",
    )
    return interval


@transaction.atomic
def delete_ad_hoc_work_interval(
    *, user: AbstractBaseUser, interval: WorkInterval
) -> None:
    if not can_manage_attendance(user):
        raise AttendanceConflictError(
            "Ad-hoc práci může zrušit jen vedoucí nebo administrátor."
        )
    if interval.shift_id is not None:
        raise AttendanceConflictError(
            "Tento záznam patří ke směně — použijte zrušení u směny."
        )
    pk = interval.pk
    interval.delete()
    _audit(user, "attendance.ad_hoc_delete", "WorkInterval", pk, "")



@transaction.atomic
def propose_from_published_shifts(
    employee: Employee, year: int, month: int
) -> list[WorkInterval]:
    """Vytvoří/obnoví návrhy WorkInterval z publikovaných směn práce."""
    created: list[WorkInterval] = []
    for shift in published_work_shifts_for_month(employee, year, month):
        if Absence.objects.filter(shift=shift).exists():
            continue
        day = shift_local_day(shift)
        employment = employment_for_day(employee, day)
        if employment is None:
            continue
        existing = (
            WorkInterval.objects.select_for_update()
            .filter(shift=shift)
            .order_by("-id")
            .first()
        )
        if existing and existing.status == WorkInterval.Status.CONFIRMED:
            continue
        break_m = _proposed_break_minutes(shift)
        if existing:
            if (
                existing.starts_at != shift.starts_at
                or existing.ends_at != shift.ends_at
                or existing.break_minutes != break_m
                or existing.workplace_id != shift.workplace_id
                or existing.employment_id != employment.pk
            ):
                existing.starts_at = shift.starts_at
                existing.ends_at = shift.ends_at
                existing.break_minutes = break_m
                existing.workplace = shift.workplace
                existing.employment = employment
                existing.status = WorkInterval.Status.DRAFT
                existing.version += 1
                existing.save()
            created.append(existing)
        else:
            interval = WorkInterval.objects.create(
                employment=employment,
                workplace=shift.workplace,
                shift=shift,
                starts_at=shift.starts_at,
                ends_at=shift.ends_at,
                break_minutes=break_m,
                status=WorkInterval.Status.DRAFT,
            )
            created.append(interval)
    return created


@transaction.atomic
def confirm_work_interval(
    *,
    user: AbstractBaseUser,
    shift: Shift,
    starts_at=None,
    ends_at=None,
    break_minutes: int | None = None,
    expected_version: int | None = None,
    note: str = "",
) -> WorkInterval:
    if not is_published_work_shift(shift):
        raise AttendanceConflictError(
            "Potvrdit lze jen publikovanou směnu práce."
        )
    day = shift_local_day(shift)
    employment = employment_for_day(shift.employee, day)
    if employment is None:
        raise AttendanceConflictError(
            MISSING_EMPLOYMENT_MSG,
            code=MISSING_EMPLOYMENT_CODE,
        )
    if Absence.objects.filter(shift=shift).exists():
        raise AttendanceConflictError(
            "Na této směně je zapsaná absence — nejdříve ji zrušte."
        )

    list(
        WorkInterval.objects.select_for_update()
        .filter(shift=shift)
        .only("id")
    )
    interval = (
        WorkInterval.objects.select_for_update()
        .filter(shift=shift)
        .order_by("-id")
        .first()
    )
    start = starts_at if starts_at is not None else shift.starts_at
    end = ends_at if ends_at is not None else shift.ends_at
    pause = (
        break_minutes
        if break_minutes is not None
        else _proposed_break_minutes(shift)
    )
    if end <= start:
        raise AttendanceConflictError(
            {"ends_at": "Konec musí být později než začátek."}
        )
    if interval is None:
        interval = WorkInterval(
            employment=employment,
            workplace=shift.workplace,
            shift=shift,
            starts_at=start,
            ends_at=end,
            break_minutes=pause,
            version=1,
        )
    else:
        if (
            expected_version is not None
            and interval.version != expected_version
        ):
            raise AttendanceConflictError(
                "Záznam byl mezitím změněn jiným uživatelem. Obnovte stránku."
            )
        interval.employment = employment
        interval.workplace = shift.workplace
        interval.starts_at = start
        interval.ends_at = end
        interval.break_minutes = pause
        interval.version += 1

    interval.status = WorkInterval.Status.CONFIRMED
    interval.confirmed_by = user if getattr(user, "is_authenticated", False) else None
    interval.confirmed_at = timezone.now()
    interval.note = (note or "")[:255]
    interval.full_clean()
    interval.save()
    _audit(
        user,
        "attendance.confirm_work",
        "WorkInterval",
        interval.pk,
        f"shift={shift.pk}; {start}–{end}; pauza={pause}",
    )
    return interval


@transaction.atomic
def set_absence_for_shift(
    *,
    user: AbstractBaseUser,
    shift: Shift,
    absence_type: AbsenceType,
    note: str = "",
) -> Absence:
    from .common import is_published_leave_shift

    if not (is_published_work_shift(shift) or is_published_leave_shift(shift)):
        raise AttendanceConflictError(
            "Absenci lze zapsat jen k publikované směně práce nebo dovolené."
        )
    day = shift_local_day(shift)
    holidays = holidays_for_year(day.year)
    # Svátek bez směny se sem nedostane; při souběhu svátku a směny evidujeme
    # absenci vůči plánu (ne dvojí odečet 8 h — minuty bereme ze směny).
    employment = employment_for_day(shift.employee, day)
    if employment is None:
        raise AttendanceConflictError(
            MISSING_EMPLOYMENT_MSG,
            code=MISSING_EMPLOYMENT_CODE,
        )
    confirmed = WorkInterval.objects.filter(
        shift=shift, status=WorkInterval.Status.CONFIRMED
    )
    if confirmed.exists():
        raise AttendanceConflictError(
            "Na této směně je potvrzená práce — nejdříve ji zrušte."
        )

    WorkInterval.objects.filter(shift=shift).delete()
    missed = shift.planned_net_minutes()
    existing = (
        Absence.objects.select_for_update().filter(shift=shift).first()
    )
    detail_holiday = ""
    if day in holidays:
        detail_holiday = f"; svátek={holidays[day]}"

    if existing:
        existing.employment = employment
        existing.absence_type = absence_type
        existing.day = day
        existing.planned_missed_minutes = missed
        existing.status = Absence.Status.APPROVED
        existing.note = (note or "")[:255]
        existing.created_by = (
            user if getattr(user, "is_authenticated", False) else None
        )
        existing.save()
        absence = existing
        op = "attendance.update_absence"
    else:
        absence = Absence.objects.create(
            employment=employment,
            absence_type=absence_type,
            shift=shift,
            day=day,
            planned_missed_minutes=missed,
            status=Absence.Status.APPROVED,
            note=(note or "")[:255],
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )
        op = "attendance.set_absence"
    _audit(
        user,
        op,
        "Absence",
        absence.pk,
        f"shift={shift.pk}; type={absence_type.code}; missed={missed}{detail_holiday}",
    )
    return absence


@transaction.atomic
def clear_attendance_for_shift(
    *, user: AbstractBaseUser, shift: Shift
) -> None:
    """Zruší potvrzenou práci i absenci u směny (vrátí den do nevyřešeno)."""
    deleted_wi = WorkInterval.objects.filter(shift=shift).delete()[0]
    deleted_ab = Absence.objects.filter(shift=shift).delete()[0]
    if deleted_wi or deleted_ab:
        _audit(
            user,
            "attendance.clear",
            "Shift",
            shift.pk,
            f"work_intervals={deleted_wi}; absences={deleted_ab}",
        )

