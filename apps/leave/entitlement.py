"""Výpočet nároku dovolené dle § 212–213 ZP (naběhlé + odhad)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.db.models import Q, Sum
from django.utils import timezone

from apps.employees.models import Employment, WorkTimeProfile
from apps.shifts.models import Shift, ShiftType

from .models import EmployeeLeaveSettings, LeavePolicySettings


def weekly_minutes_for_employment(employment: Employment, day: date) -> int:
    profile = (
        WorkTimeProfile.objects.filter(
            employment=employment,
            is_active=True,
            valid_from__lte=day,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=day))
        .order_by("-valid_from")
        .first()
    )
    if profile:
        return int(profile.agreed_weekly_minutes)
    return 2400


def weeks_for_employment(employment: Employment, policy: LeavePolicySettings) -> int:
    settings = EmployeeLeaveSettings.objects.filter(employment=employment).first()
    extra = int(settings.extra_weeks) if settings else 0
    if employment.pay_regime == Employment.PayRegime.SALARY:
        base = policy.default_weeks_salary
    else:
        base = policy.default_weeks_wage
    return base + extra


@dataclass(frozen=True)
class EntitlementBreakdown:
    accrued_minutes: int
    estimated_minutes: int
    weekly_minutes: int
    weeks: int
    accrued_multiples: int
    estimated_multiples: int
    employment_days: int
    qualifies: bool
    note: str


def _ceil_hours_to_minutes(raw_minutes: float) -> int:
    """Zaokrouhlení výsledného práva nahoru na celé hodiny (§ 213 praxe)."""
    if raw_minutes <= 0:
        return 0
    hours = math.ceil(raw_minutes / 60.0 - 1e-9)
    return int(hours * 60)


def _employment_span_in_year(employment: Employment, year: int) -> tuple[date, date] | None:
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    start = max(employment.started_on, year_start)
    end = employment.ended_on or year_end
    end = min(end, year_end)
    if end < start:
        return None
    return start, end


def _minutes_from_formula(multiples: int, weekly: int, weeks: int) -> int:
    if multiples <= 0 or weekly <= 0 or weeks <= 0:
        return 0
    if multiples >= 52:
        return weeks * weekly
    raw = (multiples / 52.0) * weekly * weeks
    return min(weeks * weekly, _ceil_hours_to_minutes(raw))


def _confirmed_work_minutes(employment: Employment, year: int) -> int:
    from apps.attendance.models import WorkInterval

    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    tz = timezone.get_current_timezone()
    range_start = timezone.make_aware(datetime.combine(year_start, time.min), tz)
    range_end = timezone.make_aware(
        datetime.combine(year_end + timedelta(days=1), time.min), tz
    )
    qs = WorkInterval.objects.filter(
        employment=employment,
        status=WorkInterval.Status.CONFIRMED,
        starts_at__gte=range_start,
        starts_at__lt=range_end,
    )
    total = 0
    for wi in qs:
        total += wi.net_minutes()
    return total


def _leave_absence_minutes(employment: Employment, year: int) -> int:
    """Náhradní doba MVP: schválená absence typu dovolena."""
    from apps.attendance.models import Absence

    total = (
        Absence.objects.filter(
            employment=employment,
            day__year=year,
            status=Absence.Status.APPROVED,
            absence_type__code="dovolena",
        ).aggregate(s=Sum("planned_missed_minutes"))["s"]
        or 0
    )
    return int(total)


def _future_work_shift_minutes(
    employment: Employment, year: int, *, from_day: date
) -> int:
    """Publikované směny práce od from_day do konce roku (odhad)."""
    employee = employment.employee
    year_end = date(year, 12, 31)
    if from_day > year_end:
        return 0
    start_day = max(from_day, date(year, 1, 1))
    if employment.started_on > start_day:
        start_day = employment.started_on
    end_day = year_end
    if employment.ended_on and employment.ended_on < end_day:
        end_day = employment.ended_on
    if end_day < start_day:
        return 0
    tz = timezone.get_current_timezone()
    range_start = timezone.make_aware(datetime.combine(start_day, time.min), tz)
    range_end = timezone.make_aware(
        datetime.combine(end_day + timedelta(days=1), time.min), tz
    )
    shifts = (
        Shift.objects.filter(
            employee=employee,
            status=Shift.Status.PUBLISHED,
            starts_at__gte=range_start,
            starts_at__lt=range_end,
            shift_type__kind=ShiftType.Kind.WORK,
            shift_type__counts_as_work=True,
        )
        .select_related("shift_type")
        .order_by("starts_at")
    )
    total = 0
    for s in shifts:
        total += s.planned_net_minutes()
    return total


def compute_entitlement_breakdown(
    employment: Employment, year: int, *, today: date | None = None
) -> EntitlementBreakdown:
    """Naběhlé + odhadované minuty dle § 212–213 (zjednodušené náhradní doby)."""
    policy = LeavePolicySettings.load()
    weeks = weeks_for_employment(employment, policy)
    mid = date(year, 7, 1)
    weekly = weekly_minutes_for_employment(employment, mid)
    span = _employment_span_in_year(employment, year)
    if span is None:
        return EntitlementBreakdown(
            accrued_minutes=0,
            estimated_minutes=0,
            weekly_minutes=weekly,
            weeks=weeks,
            accrued_multiples=0,
            estimated_multiples=0,
            employment_days=0,
            qualifies=False,
            note="vztah mimo rok",
        )
    start, end = span
    employment_days = (end - start).days + 1
    today = today or timezone.localdate()

    worked = _confirmed_work_minutes(employment, year) + _leave_absence_minutes(
        employment, year
    )
    accrued_multiples = worked // weekly if weekly else 0

    # Odhad: naběhlé + budoucí plán práce (u minulého roku jen historie)
    if year < today.year:
        estimate_from = date(year, 12, 31) + timedelta(days=1)  # nic budoucího
    elif year > today.year:
        estimate_from = start
    else:
        estimate_from = max(start, today)
    future = _future_work_shift_minutes(employment, year, from_day=estimate_from)
    # U budoucích směn nepřipočítávat dny už pokryté potvrzenou prací hrubě:
    # bereme max(worked, worked_bez_budoucna) + future; worked už je skutečnost.
    estimated_base_minutes = worked + future
    estimated_multiples = (
        estimated_base_minutes // weekly if weekly else 0
    )

    qualifies_base = employment_days >= 28
    accrued_ok = qualifies_base and accrued_multiples >= 4
    estimate_ok = qualifies_base and estimated_multiples >= 4

    accrued = (
        _minutes_from_formula(accrued_multiples, weekly, weeks) if accrued_ok else 0
    )
    estimated = (
        _minutes_from_formula(estimated_multiples, weekly, weeks)
        if estimate_ok
        else 0
    )
    # Odhad nesmí být nižší než naběhlé
    estimated = max(estimated, accrued)

    note = (
        f"§213: výměra {weeks} týdnů, týdenní {weekly} min; "
        f"naběhlé násobky {accrued_multiples} ({worked} min), "
        f"odhad násobky {estimated_multiples} (+plán {future} min); "
        f"poměr {employment_days} dní"
    )
    return EntitlementBreakdown(
        accrued_minutes=accrued,
        estimated_minutes=estimated,
        weekly_minutes=weekly,
        weeks=weeks,
        accrued_multiples=accrued_multiples,
        estimated_multiples=estimated_multiples,
        employment_days=employment_days,
        qualifies=qualifies_base,
        note=note[:255],
    )


def compute_entitled_minutes(employment: Employment, year: int) -> tuple[int, str]:
    """Zpětná kompatibilita: vrací odhad + poznámku."""
    b = compute_entitlement_breakdown(employment, year)
    return b.estimated_minutes, b.note
