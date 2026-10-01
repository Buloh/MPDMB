"""Služby nároku a plánu dovolené."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet, Sum
from django.utils import timezone

from apps.core.dashboard import can_manage_directory
from apps.core.models import AuditEvent
from apps.employees.models import Employee, Employment
from apps.employees.services import employment_for_day
from apps.shifts.fund import format_hours
from apps.shifts.models import Shift, ShiftType
from apps.workplaces.models import EmployeeWorkplace, Workplace

from .entitlement import (
    compute_entitlement_breakdown,
    compute_entitled_minutes,
    weeks_for_employment,
    weekly_minutes_for_employment,
)
from .models import (
    EmployeeLeaveSettings,
    LeaveEntitlement,
    LeavePlan,
    LeavePlanDay,
    LeavePolicySettings,
)


class LeaveConflictError(ValidationError):
    """Konflikt plánu dovolené."""


def can_manage_leave(user: AbstractBaseUser) -> bool:
    return can_manage_directory(user)


def can_access_employee_leave(user: AbstractBaseUser, employee: Employee) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if can_manage_leave(user):
        return True
    return bool(employee.user_id and employee.user_id == user.pk)


def _audit(user, operation: str, object_type: str, object_id, detail: str = "") -> None:
    AuditEvent.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        operation=operation,
        object_type=object_type,
        object_id=str(object_id),
        detail=detail,
    )


def leave_shift_type() -> ShiftType:
    st, _ = ShiftType.objects.get_or_create(
        code="D",
        defaults={
            "name": "Dovolená",
            "kind": ShiftType.Kind.LEAVE,
            "start_time": time(8, 0),
            "end_time": time(16, 0),
            "break_minutes": 0,
            "counts_as_work": False,
            "applies_on_holiday": False,
            "is_active": True,
            "sort_order": 90,
        },
    )
    if st.kind != ShiftType.Kind.LEAVE:
        st.kind = ShiftType.Kind.LEAVE
        st.counts_as_work = False
        st.save(update_fields=["kind", "counts_as_work"])
    return st


def effective_flag(
    employment: Employment,
    policy: LeavePolicySettings,
    name: str,
) -> bool:
    settings = EmployeeLeaveSettings.objects.filter(employment=employment).first()
    if settings is not None:
        value = getattr(settings, name, None)
        if value is not None:
            return bool(value)
    return bool(getattr(policy, name))


def continuous_working_days(
    starts_on: date,
    ends_on: date,
    *,
    count_holidays: bool,
) -> int:
    """Počet dnů Po–Pá v intervalu; svátky dle přepínače."""
    from apps.shifts.holidays import holidays_for_year

    holidays: set[date] = set()
    if not count_holidays:
        for y in range(starts_on.year, ends_on.year + 1):
            holidays.update(holidays_for_year(y).keys())
    n = 0
    cur = starts_on
    while cur <= ends_on:
        if cur.weekday() < 5:
            if count_holidays or cur not in holidays:
                n += 1
        cur += timedelta(days=1)
    return n


@transaction.atomic
def ensure_entitlement(employment: Employment, year: int) -> LeaveEntitlement | None:
    """Vytvoří/aktualizuje nárok. None = vztah mimo rok (bez persistování)."""
    breakdown = compute_entitlement_breakdown(employment, year)
    if breakdown.employment_days == 0 and breakdown.note == "vztah mimo rok":
        # Úklid případného prázdného záznamu z dřívějška
        LeaveEntitlement.objects.filter(employment=employment, year=year).filter(
            carried_in_minutes=0,
            planned_minutes=0,
            taken_minutes=0,
            entitled_minutes=0,
            accrued_minutes=0,
        ).delete()
        return None

    obj, created = LeaveEntitlement.objects.select_for_update().get_or_create(
        employment=employment,
        year=year,
        defaults={
            "entitled_minutes": breakdown.estimated_minutes,
            "accrued_minutes": breakdown.accrued_minutes,
            "source_note": breakdown.note,
            "must_use_by": None,
            "preferred_use_by": date(year, 12, 31),
            "statutory_latest_use_by": (
                date(year + 1, 12, 31)
                if breakdown.estimated_minutes > 0 or breakdown.accrued_minutes > 0
                else None
            ),
            "deadlines_manual": False,
        },
    )
    obj.entitled_minutes = breakdown.estimated_minutes
    obj.accrued_minutes = breakdown.accrued_minutes
    obj.source_note = breakdown.note
    # § 218 odst. 3: převod z roku Y-1 vyčerpat nejpozději do konce roku Y.
    if obj.carried_in_minutes > 0:
        obj.must_use_by = date(year, 12, 31)
    else:
        obj.must_use_by = None
    if not obj.deadlines_manual:
        obj.apply_default_deadlines()
    obj.save()
    refresh_planned_minutes(obj)
    return obj


def refresh_planned_minutes(entitlement: LeaveEntitlement) -> None:
    total = (
        LeavePlan.objects.filter(
            employment=entitlement.employment,
            year=entitlement.year,
            status=LeavePlan.Status.APPROVED,
        ).aggregate(s=Sum("total_minutes"))["s"]
        or 0
    )
    if entitlement.planned_minutes != total:
        entitlement.planned_minutes = total
        entitlement.save(update_fields=["planned_minutes", "updated_at"])


def own_leave_warn_flags(
    entitlement: LeaveEntitlement, *, today: date | None = None
) -> dict[str, bool]:
    """Varování pro vlastní nárok roku (§ 218) — ne převod."""
    if today is None:
        today = timezone.localdate()
    remaining = entitlement.own_year_remaining_minutes
    preferred = entitlement.preferred_use_by or entitlement.default_preferred_use_by()
    latest = entitlement.statutory_latest_use_by
    if latest is None and not entitlement.deadlines_manual:
        latest = entitlement.default_statutory_latest_use_by()
    warn_own_year = bool(remaining > 0 and today > preferred)
    warn_own_deadline = False
    if remaining > 0 and latest is not None:
        warn_own_deadline = today >= latest - timedelta(days=90)
    return {
        "warn_own_year": warn_own_year,
        "warn_own_deadline": warn_own_deadline,
    }


def employees_for_leave_year(user: AbstractBaseUser) -> QuerySet[Employee]:
    if can_manage_leave(user):
        return Employee.objects.filter(is_active=True).order_by(
            "last_name", "first_name"
        )
    return Employee.objects.filter(user_id=user.pk, is_active=True)


def primary_workplace(employee: Employee, day: date) -> Workplace | None:
    from django.db.models import Q

    link = (
        EmployeeWorkplace.objects.filter(
            employee=employee,
            valid_from__lte=day,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=day))
        .select_related("workplace")
        .order_by("-valid_from")
        .first()
    )
    return link.workplace if link else None


def iter_leave_days(starts_on: date, ends_on: date) -> list[date]:
    """Pracovní dny Po–Pá v intervalu (MVP)."""
    days: list[date] = []
    cur = starts_on
    while cur <= ends_on:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days


def minutes_per_leave_day(employment: Employment, day: date) -> int:
    weekly = weekly_minutes_for_employment(employment, day)
    return max(1, weekly // 5)


def preview_plan_minutes(
    employment: Employment,
    starts_on: date,
    ends_on: date,
    portion: str = LeavePlanDay.Portion.FULL,
) -> int:
    days = iter_leave_days(starts_on, ends_on)
    return sum(portion_minutes(employment, d, portion) for d in days)


def format_leave_balance(minutes: int, daily_minutes: int) -> str:
    """Zobrazení nároku: dny (1 desetinné) + hodiny, např. 20,0 d (160:00)."""
    daily = max(1, int(daily_minutes))
    days = minutes / daily
    days_label = f"{days:.1f}".replace(".", ",")
    return f"{days_label} d ({format_hours(minutes)})"


def reference_daily_minutes(employment: Employment, year: int) -> int:
    return minutes_per_leave_day(employment, date(year, 7, 1))


def half_day_allowed(employment: Employment) -> bool:
    policy = LeavePolicySettings.load()
    return effective_flag(employment, policy, "allow_half_day")


def portion_minutes(
    employment: Employment, day: date, portion: str
) -> int:
    daily = minutes_per_leave_day(employment, day)
    if portion in (LeavePlanDay.Portion.AM, LeavePlanDay.Portion.PM, "am", "pm"):
        return max(1, daily // 2)
    return daily


def leave_window_for_day(
    day: date, portion: str, shift_type: ShiftType | None = None
) -> tuple[datetime, datetime]:
    """Okno pro kontrolu překryvu / vytvoření směny (naive local)."""
    st = shift_type or leave_shift_type()
    start_t = st.start_time
    end_t = st.end_time
    start_naive = datetime.combine(day, start_t)
    end_naive = datetime.combine(day, end_t)
    if end_t <= start_t:
        end_naive += timedelta(days=1)
    full_minutes = max(
        1, int((end_naive - start_naive).total_seconds() // 60)
    )
    half = full_minutes // 2
    if portion in (LeavePlanDay.Portion.AM, "am"):
        return start_naive, start_naive + timedelta(minutes=half)
    if portion in (LeavePlanDay.Portion.PM, "pm"):
        mid = start_naive + timedelta(minutes=half)
        return mid, end_naive
    return start_naive, end_naive



def year_overview(*, user: AbstractBaseUser, year: int) -> dict:
    policy = LeavePolicySettings.load()
    employees = list(
        employees_for_leave_year(user).prefetch_related(
            "employments", "employments__leave_settings"
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
        ent = ensure_entitlement(employment, year)
        if ent is None:
            continue
        daily = reference_daily_minutes(employment, year)
        warns = own_leave_warn_flags(ent)
        rows.append(
            {
                "employee": emp,
                "employment": employment,
                "entitlement": ent,
                "accrued_label": format_leave_balance(ent.accrued_minutes, daily),
                "entitled_label": format_leave_balance(ent.entitled_minutes, daily),
                "carried_label": format_leave_balance(ent.carried_in_minutes, daily),
                "planned_label": format_leave_balance(ent.planned_minutes, daily),
                "remaining_label": format_leave_balance(ent.remaining_minutes, daily),
                "accrued_remaining_label": format_leave_balance(
                    ent.accrued_remaining_minutes, daily
                ),
                "warn_carryover": bool(
                    policy.warn_unused_carryover
                    and ent.carried_in_minutes
                    and ent.must_use_by
                    and ent.must_use_by <= date(year, 12, 31)
                    and ent.remaining_minutes > 0
                ),
                "warn_own_year": warns["warn_own_year"],
                "warn_own_deadline": warns["warn_own_deadline"],
            }
        )
    return {
        "year": year,
        "rows": rows,
        "can_manage": can_manage_leave(user),
        "policy": policy,
        "format_hours": format_hours,
    }


def employee_year_detail(
    *, user: AbstractBaseUser, employee: Employee, year: int
) -> dict:
    if not can_access_employee_leave(user, employee):
        raise PermissionError("Nemáte oprávnění k dovolené tohoto zaměstnance.")
    employment = employment_for_day(employee, date(year, 7, 1)) or (
        employee.employments.filter(is_active=True).order_by("-started_on").first()
    )
    if employment is None:
        raise LeaveConflictError("Zaměstnanec nemá aktivní pracovní vztah.")
    if employment.relation_type != Employment.RelationType.EMPLOYMENT:
        raise LeaveConflictError(
            "Modul dovolené zatím podporuje jen pracovní poměr (ne DPP/DPČ)."
        )
    ent = ensure_entitlement(employment, year)
    if ent is None:
        raise LeaveConflictError("Pracovní vztah v tomto kalendářním roce neplatí.")
    plans = list(
        LeavePlan.objects.filter(employment=employment, year=year)
        .exclude(status=LeavePlan.Status.CANCELLED)
        .order_by("starts_on")
    )
    daily = reference_daily_minutes(employment, year)
    from .calendar_view import year_calendar_for_employment

    warns = own_leave_warn_flags(ent)
    return {
        "year": year,
        "employee": employee,
        "employment": employment,
        "entitlement": ent,
        "accrued_label": format_leave_balance(ent.accrued_minutes, daily),
        "entitled_label": format_leave_balance(ent.entitled_minutes, daily),
        "carried_label": format_leave_balance(ent.carried_in_minutes, daily),
        "planned_label": format_leave_balance(ent.planned_minutes, daily),
        "remaining_label": format_leave_balance(ent.remaining_minutes, daily),
        "accrued_remaining_label": format_leave_balance(
            ent.accrued_remaining_minutes, daily
        ),
        "plans": plans,
        "can_manage": can_manage_leave(user),
        "policy": LeavePolicySettings.load(),
        "allow_half_day": half_day_allowed(employment),
        "calendar_months": year_calendar_for_employment(employment, year),
        "weekday_headers": ("Po", "Út", "St", "Čt", "Pá", "So", "Ne"),
        "warn_own_year": warns["warn_own_year"],
        "warn_own_deadline": warns["warn_own_deadline"],
    }


@transaction.atomic
def create_leave_plan(
    *,
    user: AbstractBaseUser,
    employment: Employment,
    year: int,
    starts_on: date,
    ends_on: date,
    note: str = "",
    approve: bool = False,
    portion: str = LeavePlanDay.Portion.FULL,
) -> LeavePlan:
    if not can_manage_leave(user):
        raise LeaveConflictError("Plán dovolené může založit jen vedoucí nebo administrátor.")
    if ends_on < starts_on:
        raise LeaveConflictError({"ends_on": "Konec musí být později než začátek."})
    if starts_on.year != year or ends_on.year != year:
        raise LeaveConflictError("Blok musí ležet v zvoleném kalendářním roce.")
    portion = portion or LeavePlanDay.Portion.FULL
    if portion not in LeavePlanDay.Portion.values:
        raise LeaveConflictError("Neplatná část dne.")
    if portion != LeavePlanDay.Portion.FULL:
        if starts_on != ends_on:
            raise LeaveConflictError(
                "Půldenní dovolená je možná jen u jednodenního bloku."
            )
        if not half_day_allowed(employment):
            raise LeaveConflictError(
                "Půldenní dovolená není u tohoto zaměstnance povolena."
            )
    days = iter_leave_days(starts_on, ends_on)
    if not days:
        raise LeaveConflictError("V intervalu není žádný pracovní den (Po–Pá).")
    total = preview_plan_minutes(employment, starts_on, ends_on, portion)
    entitlement = ensure_entitlement(employment, year)
    if entitlement is None:
        raise LeaveConflictError("Pracovní vztah v tomto kalendářním roce neplatí.")
    if total > entitlement.remaining_minutes:
        raise LeaveConflictError(
            f"Nedostatečný zůstatek dovolené (odhad) "
            f"({format_hours(entitlement.remaining_minutes)} zbývá, "
            f"blok má {format_hours(total)})."
        )
    policy = LeavePolicySettings.load()
    if effective_flag(employment, policy, "block_overlap_with_work_shifts"):
        _ensure_no_work_overlap(employment.employee, days, portion)

    plan = LeavePlan.objects.create(
        employment=employment,
        year=year,
        starts_on=starts_on,
        ends_on=ends_on,
        total_minutes=total,
        portion=portion,
        status=LeavePlan.Status.DRAFT,
        note=(note or "")[:255],
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    _audit(user, "leave.plan_create", "LeavePlan", plan.pk, f"{starts_on}–{ends_on}")
    if approve:
        return approve_leave_plan(user=user, plan=plan)
    return plan


def _ensure_no_work_overlap(
    employee: Employee, days: list[date], portion: str = LeavePlanDay.Portion.FULL
) -> None:
    tz = timezone.get_current_timezone()
    st = leave_shift_type()
    for day in days:
        win_start, win_end = leave_window_for_day(day, portion, st)
        start = timezone.make_aware(win_start, tz)
        end = timezone.make_aware(win_end, tz)
        conflict = (
            Shift.objects.filter(
                employee=employee,
                status=Shift.Status.PUBLISHED,
                starts_at__lt=end,
                ends_at__gt=start,
                shift_type__kind=ShiftType.Kind.WORK,
            )
            .exclude(status=Shift.Status.CANCELLED)
            .exists()
        )
        if conflict:
            raise LeaveConflictError(
                f"Dne {day:%d.%m.%Y} je publikovaná směna práce v tomto úseku — "
                f"nejprve ji upravte v dlouhodobém plánu."
            )


@transaction.atomic
def approve_leave_plan(*, user: AbstractBaseUser, plan: LeavePlan) -> LeavePlan:
    if not can_manage_leave(user):
        raise LeaveConflictError("Schválit může jen vedoucí nebo administrátor.")
    plan = LeavePlan.objects.select_for_update().get(pk=plan.pk)
    if plan.status == LeavePlan.Status.APPROVED:
        return plan
    if plan.status == LeavePlan.Status.CANCELLED:
        raise LeaveConflictError("Zrušený plán nelze schválit.")

    portion = plan.portion or LeavePlanDay.Portion.FULL
    if portion != LeavePlanDay.Portion.FULL and not half_day_allowed(plan.employment):
        raise LeaveConflictError(
            "Půldenní dovolená není u tohoto zaměstnance povolena."
        )

    entitlement = ensure_entitlement(plan.employment, plan.year)
    if entitlement is None:
        raise LeaveConflictError("Pracovní vztah v tomto kalendářním roce neplatí.")
    # remaining bez tohoto návrhu (návrh ještě není v planned)
    if plan.total_minutes > entitlement.remaining_minutes:
        raise LeaveConflictError("Nedostatečný zůstatek (odhad) při schválení.")

    warning = None
    if plan.total_minutes > entitlement.accrued_remaining_minutes:
        warning = (
            "Schváleno oproti odhadovanému nároku; naběhlé zatím "
            f"{format_hours(entitlement.accrued_minutes)} "
            f"(zůstatek naběhlého {format_hours(entitlement.accrued_remaining_minutes)})."
        )

    policy = LeavePolicySettings.load()
    days = iter_leave_days(plan.starts_on, plan.ends_on)
    if effective_flag(plan.employment, policy, "block_overlap_with_work_shifts"):
        _ensure_no_work_overlap(plan.employment.employee, days, portion)
    if effective_flag(plan.employment, policy, "enforce_continuous_block"):
        span = continuous_working_days(
            plan.starts_on,
            plan.ends_on,
            count_holidays=bool(policy.continuous_count_holidays),
        )
        if span < policy.continuous_min_days:
            raise LeaveConflictError(
                f"Souvislý úsek musí mít alespoň {policy.continuous_min_days} "
                f"pracovních dnů Po–Pá"
                f"{' včetně svátků' if policy.continuous_count_holidays else ' (bez svátků)'}"
                f" (nyní {span}). Kontrolu lze vypnout v pravidlech dovolené."
            )

    st = leave_shift_type()
    employee = plan.employment.employee
    tz = timezone.get_current_timezone()
    LeavePlanDay.objects.filter(plan=plan).delete()
    for day in days:
        minutes = portion_minutes(plan.employment, day, portion)
        workplace = primary_workplace(employee, day)
        if workplace is None:
            workplace = (
                Workplace.objects.filter(is_active=True).order_by("name").first()
            )
        if workplace is None:
            raise LeaveConflictError("Chybí pracoviště pro zápis směny dovolené.")
        win_start, win_end = leave_window_for_day(day, portion, st)
        # délka podle nároku (úvazek), okno podle typu D
        starts_at = timezone.make_aware(win_start, tz)
        ends_at = starts_at + timedelta(minutes=minutes)
        # u PM držet začátek v odpolední polovině typu D
        if portion in (LeavePlanDay.Portion.PM, "pm"):
            ends_at = timezone.make_aware(win_end, tz)
            starts_at = ends_at - timedelta(minutes=minutes)
        note_extra = ""
        if portion == LeavePlanDay.Portion.AM:
            note_extra = " dopoledne"
        elif portion == LeavePlanDay.Portion.PM:
            note_extra = " odpoledne"
        shift = Shift.objects.create(
            employee=employee,
            workplace=workplace,
            shift_type=st,
            starts_at=starts_at,
            ends_at=ends_at,
            status=Shift.Status.PUBLISHED,
            note=f"Dovolená plán #{plan.pk}{note_extra}",
        )
        LeavePlanDay.objects.create(
            plan=plan,
            day=day,
            minutes=minutes,
            portion=portion,
            shift=shift,
        )
        _ensure_leave_absence(user=user, shift=shift, minutes=minutes)

    plan.status = LeavePlan.Status.APPROVED
    plan.approved_by = user if getattr(user, "is_authenticated", False) else None
    plan.version += 1
    plan.total_minutes = sum(d.minutes for d in plan.days.all())
    plan.save()
    refresh_planned_minutes(entitlement)
    _audit(user, "leave.plan_approve", "LeavePlan", plan.pk, warning or "")
    if warning:
        plan._leave_warning = warning  # type: ignore[attr-defined]
    return plan


def _ensure_leave_absence(*, user, shift: Shift, minutes: int) -> None:
    """Propsání schválené dovolené do docházky jako absence typu dovolena."""
    from apps.attendance.models import Absence, AbsenceType
    from apps.employees.services import employment_for_day as emp_for_day

    day = timezone.localtime(shift.starts_at).date()
    absence_type = AbsenceType.objects.filter(code="dovolena", is_active=True).first()
    if absence_type is None:
        return
    employment = emp_for_day(shift.employee, day)
    if employment is None:
        return
    existing = Absence.objects.filter(shift=shift).first()
    if existing:
        existing.planned_missed_minutes = minutes
        existing.absence_type = absence_type
        existing.status = Absence.Status.APPROVED
        existing.save(
            update_fields=[
                "planned_missed_minutes",
                "absence_type",
                "status",
                "updated_at",
            ]
        )
        return
    Absence.objects.create(
        employment=employment,
        absence_type=absence_type,
        shift=shift,
        day=day,
        planned_missed_minutes=minutes,
        status=Absence.Status.APPROVED,
        note="Schválený plán dovolené",
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )

@transaction.atomic
def cancel_leave_plan(*, user: AbstractBaseUser, plan: LeavePlan) -> LeavePlan:
    if not can_manage_leave(user):
        raise LeaveConflictError("Zrušit může jen vedoucí nebo administrátor.")
    plan = LeavePlan.objects.select_for_update().get(pk=plan.pk)
    if plan.status == LeavePlan.Status.CANCELLED:
        return plan
    from apps.attendance.models import Absence

    for day in plan.days.select_related("shift"):
        if day.shift_id:
            Absence.objects.filter(shift_id=day.shift_id).delete()
            day.shift.delete()
    plan.days.all().delete()
    plan.status = LeavePlan.Status.CANCELLED
    plan.version += 1
    plan.save(update_fields=["status", "version", "updated_at"])
    entitlement = ensure_entitlement(plan.employment, plan.year)
    if entitlement is not None:
        refresh_planned_minutes(entitlement)
    _audit(user, "leave.plan_cancel", "LeavePlan", plan.pk, "")
    return plan
