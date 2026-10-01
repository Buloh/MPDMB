"""Služby pro zápis zaměstnanců, vztahů a kvalifikací."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from apps.core.dashboard import can_manage_directory
from apps.core.models import AuditEvent

from .models import (
    BalancingPeriod,
    Employee,
    EmployeeQualification,
    Employment,
    WorkTimeProfile,
)
from .user_sync import sync_user_from_employee


def employment_for_day(employee: Employee, day: date) -> Employment | None:
    """Aktivní pracovní vztah platný v daný kalendářní den."""
    from django.db.models import Q

    return (
        Employment.objects.filter(employee=employee, is_active=True)
        .filter(started_on__lte=day)
        .filter(Q(ended_on__isnull=True) | Q(ended_on__gte=day))
        .order_by("-started_on")
        .first()
    )


def _audit(user, operation: str, obj, detail: str = "") -> None:
    AuditEvent.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        operation=operation,
        object_type=obj.__class__.__name__,
        object_id=str(obj.pk),
        detail=detail,
    )


def apply_employee_work_time(
    *,
    user,
    employment: Employment,
    cleaned: dict,
    existing: WorkTimeProfile | None,
) -> WorkTimeProfile:
    """Uloží úvazek; při změně od pozdějšího data ukončí starý profil."""
    valid_from = cleaned["valid_from"]
    statutory = cleaned["statutory_weekly_minutes"]
    agreed = cleaned["agreed_weekly_minutes"]
    regime = cleaned["regime"]
    distribution = cleaned["distribution"]

    if existing is None:
        profile = WorkTimeProfile.objects.create(
            employment=employment,
            valid_from=valid_from,
            statutory_weekly_minutes=statutory,
            agreed_weekly_minutes=agreed,
            regime=regime,
            distribution=distribution,
            is_active=True,
        )
        _audit(user, "work_time_create", profile, detail=f"od {valid_from}")
        return profile

    same_terms = (
        existing.statutory_weekly_minutes == statutory
        and existing.agreed_weekly_minutes == agreed
        and existing.regime == regime
        and existing.distribution == distribution
    )
    if same_terms and valid_from == existing.valid_from:
        return existing

    if same_terms:
        existing.valid_from = valid_from
        existing.save(update_fields=["valid_from"])
        _audit(user, "work_time_update", existing, detail=f"od {valid_from}")
        return existing

    if valid_from <= existing.valid_from:
        existing.statutory_weekly_minutes = statutory
        existing.agreed_weekly_minutes = agreed
        existing.regime = regime
        existing.distribution = distribution
        existing.save(
            update_fields=[
                "statutory_weekly_minutes",
                "agreed_weekly_minutes",
                "regime",
                "distribution",
            ]
        )
        _audit(user, "work_time_update", existing, detail="změna podmínek")
        return existing

    # Změna uprostřed: ukončit starý den před novým začátkem
    existing.valid_to = valid_from - timedelta(days=1)
    existing.save(update_fields=["valid_to"])
    _audit(
        user,
        "work_time_close",
        existing,
        detail=f"do {existing.valid_to}",
    )
    profile = WorkTimeProfile.objects.create(
        employment=employment,
        valid_from=valid_from,
        statutory_weekly_minutes=statutory,
        agreed_weekly_minutes=agreed,
        regime=regime,
        distribution=distribution,
        is_active=True,
    )
    _audit(user, "work_time_create", profile, detail=f"od {valid_from}")
    return profile


@transaction.atomic
def save_employee_bundle(
    *,
    user,
    employee: Employee,
    employment: Employment | None,
    qualification_formset,
    creating: bool,
    work_time_cleaned: dict | None = None,
    workplace_formset=None,
    leave_settings_form=None,
) -> Employee:
    employee.save()
    sync_user_from_employee(employee)
    if employment is not None:
        employment.employee = employee
        if not employment.job_title and employee.job_title:
            employment.job_title = employee.job_title
        employment.save()
        _audit(
            user,
            "employment_create" if creating else "employment_update",
            employment,
            detail=f"nástup {employment.started_on}",
        )
        if work_time_cleaned:
            existing = (
                WorkTimeProfile.objects.filter(
                    employment=employment, is_active=True
                )
                .order_by("-valid_from")
                .first()
            )
            apply_employee_work_time(
                user=user,
                employment=employment,
                cleaned=work_time_cleaned,
                existing=existing,
            )
        if leave_settings_form is not None:
            leave_obj = leave_settings_form.save(commit=False)
            leave_obj.employment = employment
            leave_obj.save()
            _audit(
                user,
                "leave_settings_save",
                leave_obj,
                detail=f"half={leave_obj.allow_half_day}",
            )

    qualification_formset.instance = employee
    qualifications = qualification_formset.save(commit=False)
    for item in qualifications:
        item.employee = employee
        item.save()
        _audit(
            user,
            "qualification_save",
            item,
            detail=str(item.qualification_type_id),
        )
    for item in qualification_formset.deleted_objects:
        _audit(user, "qualification_delete", item, detail=str(item.pk))
        item.delete()

    if workplace_formset is not None:
        workplace_formset.instance = employee
        workplaces = workplace_formset.save(commit=False)
        for item in workplaces:
            item.employee = employee
            item.full_clean()
            item.save()
            _audit(
                user,
                "workplace_assign",
                item,
                detail=str(item.workplace_id),
            )
        for item in workplace_formset.deleted_objects:
            _audit(user, "workplace_unassign", item, detail=str(item.pk))
            item.delete()

    _audit(
        user,
        "employee_create" if creating else "employee_update",
        employee,
        detail=employee.internal_number,
    )
    return employee


# Zpětná kompatibilita pro starší importy.
save_employee_with_employment = save_employee_bundle


def qualification_alerts_for_user(user: AbstractBaseUser) -> list[dict]:
    """Expirované a blížící se kvalifikace pro modal na přehledu."""
    if not getattr(user, "is_authenticated", False):
        return []
    today = timezone.localdate()
    qs = EmployeeQualification.objects.filter(
        is_active=True,
        valid_until__isnull=False,
        employee__is_active=True,
    ).select_related("employee", "qualification_type")
    if can_manage_directory(user):
        pass
    else:
        qs = qs.filter(employee__user=user)
    alerts: list[dict] = []
    for item in qs.order_by("valid_until", "employee__last_name"):
        days = (item.valid_until - today).days
        warn = item.qualification_type.warn_days_before
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
                "qualification": item,
                "employee": item.employee,
                "severity": severity,
                "label": label,
                "days": days,
                "valid_until": item.valid_until,
            }
        )
    return alerts


@transaction.atomic
def archive_employee(*, user, employee: Employee) -> Employee:
    employee.is_active = False
    employee.save(update_fields=["is_active", "updated_at"])
    active = employee.employments.filter(is_active=True, ended_on__isnull=True)
    for emp in active:
        emp.is_active = False
        emp.save(update_fields=["is_active", "updated_at"])
    _audit(user, "employee_archive", employee, detail=employee.internal_number)
    return employee


def _date_ranges_overlap(
    a_start: date,
    a_end: date | None,
    b_start: date,
    b_end: date | None,
) -> bool:
    a_right = a_end or date.max
    b_right = b_end or date.max
    return a_start <= b_right and b_start <= a_right


def _active_employment_for(employee: Employee) -> Employment | None:
    return (
        employee.employments.filter(is_active=True)
        .order_by("-started_on")
        .first()
    )


@dataclass
class BulkFundResult:
    created: list = field(default_factory=list)
    skipped: list[tuple[Employee, str]] = field(default_factory=list)


@transaction.atomic
def bulk_create_work_time_profiles(
    *,
    user,
    employees,
    valid_from: date,
    statutory_weekly_minutes: int,
    agreed_weekly_minutes: int,
    regime: str,
    distribution: str,
    valid_to: date | None = None,
) -> BulkFundResult:
    """Vytvoří stejný profil pro více zaměstnanců s aktivním vztahem."""
    result = BulkFundResult()
    for employee in employees:
        employment = _active_employment_for(employee)
        if employment is None:
            result.skipped.append((employee, "chybí aktivní pracovní vztah"))
            continue
        existing = WorkTimeProfile.objects.filter(
            employment=employment,
            is_active=True,
        )
        overlap = False
        for profile in existing:
            if _date_ranges_overlap(
                profile.valid_from, profile.valid_to, valid_from, valid_to
            ):
                overlap = True
                break
        if overlap:
            result.skipped.append(
                (employee, "již má překrývající aktivní profil")
            )
            continue
        profile = WorkTimeProfile.objects.create(
            employment=employment,
            valid_from=valid_from,
            valid_to=valid_to,
            statutory_weekly_minutes=statutory_weekly_minutes,
            agreed_weekly_minutes=agreed_weekly_minutes,
            regime=regime,
            distribution=distribution,
            is_active=True,
        )
        _audit(
            user,
            "work_time_profile_bulk_create",
            profile,
            detail=f"od {valid_from}",
        )
        result.created.append(profile)
    return result


@transaction.atomic
def bulk_create_balancing_periods(
    *,
    user,
    employees,
    starts_on: date,
    ends_on: date,
    kind: str,
    auto_target: bool = True,
    target_minutes: int | None = None,
    note: str = "",
    all_with_active_profile: bool = False,
) -> BulkFundResult:
    """Vytvoří stejné vyrovnávací období pro aktivní profily vybraných."""
    result = BulkFundResult()
    if all_with_active_profile:
        profiles = list(
            WorkTimeProfile.objects.filter(is_active=True).select_related(
                "employment__employee"
            )
        )
    else:
        profiles = list(
            WorkTimeProfile.objects.filter(
                is_active=True,
                employment__employee__in=employees,
            ).select_related("employment__employee")
        )
    # Jeden aktivní profil na zaměstnance – ber nejnovější valid_from.
    by_employee: dict[int, WorkTimeProfile] = {}
    for profile in profiles:
        emp_id = profile.employment.employee_id
        current = by_employee.get(emp_id)
        if current is None or profile.valid_from > current.valid_from:
            by_employee[emp_id] = profile

    selected_ids = {e.pk for e in employees} if not all_with_active_profile else None
    if selected_ids is not None:
        for employee in employees:
            if employee.pk not in by_employee:
                result.skipped.append((employee, "chybí aktivní profil"))

    for profile in by_employee.values():
        employee = profile.employment.employee
        if BalancingPeriod.objects.filter(
            profile=profile,
            starts_on=starts_on,
            ends_on=ends_on,
            kind=kind,
        ).exists():
            result.skipped.append((employee, "stejné období už existuje"))
            continue
        if auto_target or not target_minutes:
            draft = BalancingPeriod(
                profile=profile,
                starts_on=starts_on,
                ends_on=ends_on,
                kind=kind,
                target_minutes=1,
            )
            from apps.shifts.fund import dynamic_balancing_target_minutes

            minutes = dynamic_balancing_target_minutes(draft)
        else:
            minutes = target_minutes
        period = BalancingPeriod.objects.create(
            profile=profile,
            starts_on=starts_on,
            ends_on=ends_on,
            kind=kind,
            target_minutes=minutes,
            note=note or "",
        )
        _audit(
            user,
            "balancing_period_bulk_create",
            period,
            detail=f"{starts_on}–{ends_on}",
        )
        result.created.append(period)
    return result
