"""Výpočet měsíčního fondu z úvazku a délky směny (dynamicky po dnech)."""

from __future__ import annotations

from calendar import monthrange
from collections import Counter
from datetime import date, timedelta

from django.db.models import Q

from apps.employees.models import BalancingPeriod, Employee, WorkTimeProfile

from .holidays import holidays_for_year
from .models import ScheduleTemplate, Shift, ShiftType

DEFAULT_DAILY_MINUTES = 8 * 60


def format_hours(minutes: int) -> str:
    hours = minutes // 60
    mins = minutes % 60
    if mins:
        return f"{hours}:{mins:02d}"
    return f"{hours}"


def month_day_list(year: int, month: int) -> list[date]:
    last = monthrange(year, month)[1]
    return [date(year, month, day) for day in range(1, last + 1)]


def calendar_month_fund(
    year: int, month: int, daily_minutes: int = DEFAULT_DAILY_MINUTES
) -> dict:
    """Kalendářní referenční fond: Po–Pá včetně všedních svátků × denní hodiny."""
    days = month_day_list(year, month)
    holiday_map = holidays_for_year(year)
    work_days = 0
    holiday_weekdays = 0
    for day in days:
        if day.weekday() >= 5:
            continue
        if day in holiday_map:
            holiday_weekdays += 1
        work_days += 1
    fund_minutes = work_days * daily_minutes
    holiday_minutes = holiday_weekdays * daily_minutes
    return {
        "work_days": work_days,
        "holiday_weekdays": holiday_weekdays,
        "daily_minutes": daily_minutes,
        "daily_label": format_hours(daily_minutes),
        "fund_minutes": fund_minutes,
        "fund_label": format_hours(fund_minutes),
        "holiday_minutes": holiday_minutes,
        "holiday_label": format_hours(holiday_minutes),
        "daily_source": f"kalendář × {format_hours(daily_minutes)} h/den",
        "is_continuous": False,
        "segments_label": "",
    }


def active_work_time_profile(
    employee: Employee, day: date
) -> WorkTimeProfile | None:
    employment = employee.current_employment
    if not employment:
        return None
    return (
        WorkTimeProfile.objects.filter(
            employment=employment,
            is_active=True,
            valid_from__lte=day,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=day))
        .order_by("-valid_from")
        .first()
    )


def template_work_days_per_week(template: ScheduleTemplate) -> int:
    """Počet pracovních dnů za týden podle šablony (u 14denní = max v 7denním okně)."""
    template.ensure_slots()
    by_index: dict[int, bool] = {}
    for slot in template.slots.select_related("shift_type").all():
        st = slot.shift_type
        is_work = bool(
            st
            and st.is_active
            and st.counts_as_work
            and st.kind == ShiftType.Kind.WORK
        )
        by_index[slot.day_index] = is_work
    cycle = template.cycle_length or 7
    if cycle <= 7:
        return max(1, sum(1 for i in range(cycle) if by_index.get(i)))
    best = 0
    for start in range(0, cycle, 7):
        window = sum(
            1 for i in range(start, min(start + 7, cycle)) if by_index.get(i)
        )
        best = max(best, window)
    return max(1, best)


def days_per_week_for_profile(
    profile: WorkTimeProfile, employee: Employee, day: date
) -> int:
    from .services import resolve_assignment_for_day

    days_pw = 5
    if profile.regime in (
        WorkTimeProfile.Regime.CONTINUOUS,
        WorkTimeProfile.Regime.MULTI,
    ):
        asg = resolve_assignment_for_day(employee, day)
        if asg and asg.template_id and asg.template.is_active:
            days_pw = template_work_days_per_week(asg.template)
        elif profile.regime == WorkTimeProfile.Regime.CONTINUOUS:
            days_pw = 7
    return days_pw


def daily_minutes_from_profile(
    profile: WorkTimeProfile, employee: Employee, day: date
) -> int:
    if not profile.agreed_weekly_minutes:
        return DEFAULT_DAILY_MINUTES
    days_pw = days_per_week_for_profile(profile, employee, day)
    return max(1, int(profile.agreed_weekly_minutes // days_pw))


def dominant_work_shift_type(
    employee: Employee,
    day: date,
    *,
    cells: dict | None = None,
) -> ShiftType | None:
    from .services import resolve_assignment_for_day

    asg = resolve_assignment_for_day(employee, day)
    if asg and asg.template_id and asg.template.is_active:
        asg.template.ensure_slots()
        types: list[ShiftType] = []
        for slot in asg.template.slots.select_related("shift_type").all():
            st = slot.shift_type
            if st and st.counts_as_work and st.kind == ShiftType.Kind.WORK:
                types.append(st)
        if types:
            return Counter(types).most_common(1)[0][0]
    if cells:
        counts: Counter = Counter()
        for (emp_id, _d), shifts in cells.items():
            if emp_id != employee.pk:
                continue
            for shift in shifts:
                if shift.status != Shift.Status.PUBLISHED:
                    continue
                st = shift.shift_type
                if st and st.counts_as_work and st.kind == ShiftType.Kind.WORK:
                    counts[st] += 1
        if counts:
            return counts.most_common(1)[0][0]
    return None


def resolve_daily_fund_minutes(
    employee: Employee,
    day: date,
    *,
    cells: dict | None = None,
    profile: WorkTimeProfile | None = None,
) -> tuple[int, str]:
    """Denní minuty Fondu a text zdroje (úvazek / typ směny / výchozí)."""
    profile = profile or active_work_time_profile(employee, day)
    if profile and profile.agreed_weekly_minutes:
        days_pw = days_per_week_for_profile(profile, employee, day)
        daily = max(1, int(profile.agreed_weekly_minutes // days_pw))
        source = (
            f"úvazek {format_hours(profile.agreed_weekly_minutes)} h/týden "
            f"÷ {days_pw} → {format_hours(daily)} h/den"
        )
        return daily, source
    st = dominant_work_shift_type(employee, day, cells=cells)
    if st:
        return (
            st.net_minutes(),
            f"typ směny {st.code} ({st.net_hours_label})",
        )
    return DEFAULT_DAILY_MINUTES, "výchozí 8 h/den"


def day_is_fund_eligible(
    employee: Employee,
    day: date,
    profile: WorkTimeProfile | None,
    holiday_map: dict,
    cells: dict | None,
) -> bool:
    """Zda se den započítá do fondu podle režimu účinného profilu."""
    from .services import resolve_template_type

    if profile and profile.regime == WorkTimeProfile.Regime.CONTINUOUS:
        day_shifts = (cells or {}).get((employee.pk, day), [])
        has_work = any(
            s.status == Shift.Status.PUBLISHED and s.planned_net_minutes() > 0
            for s in day_shifts
        )
        if has_work:
            return True
        st = resolve_template_type(employee, day)
        if not st or not st.counts_as_work or st.kind != ShiftType.Kind.WORK:
            return False
        if day in holiday_map and not st.applies_on_holiday:
            return False
        return True
    # Po–Pá včetně státního svátku (svátek se z fondu neodčítá).
    if day.weekday() >= 5:
        return False
    return True


def fund_minutes_for_day(
    employee: Employee,
    day: date,
    *,
    cells: dict | None = None,
    holiday_map: dict | None = None,
    profile: WorkTimeProfile | None = None,
) -> int:
    """Fondové minuty za jeden den (0 pokud den nepatří do fondu)."""
    holiday_map = holiday_map if holiday_map is not None else holidays_for_year(day.year)
    profile = profile or active_work_time_profile(employee, day)
    if not day_is_fund_eligible(employee, day, profile, holiday_map, cells):
        return 0
    daily, _source = resolve_daily_fund_minutes(
        employee, day, cells=cells, profile=profile
    )
    return daily


def fund_days_for_employee(
    employee: Employee,
    year: int,
    month: int,
    profile: WorkTimeProfile | None,
    holiday_map: dict,
    cells: dict,
) -> tuple[list[date], int]:
    """Dny do Fondu a počet vyloučených svátečních Po–Pá (běžný režim)."""
    days = month_day_list(year, month)
    fund_days: list[date] = []
    holiday_weekdays = 0
    for day in days:
        day_profile = active_work_time_profile(employee, day) or profile
        if day.weekday() < 5 and day in holiday_map:
            if not (
                day_profile
                and day_profile.regime == WorkTimeProfile.Regime.CONTINUOUS
            ):
                holiday_weekdays += 1
        if day_is_fund_eligible(
            employee, day, day_profile, holiday_map, cells
        ):
            fund_days.append(day)
    return fund_days, holiday_weekdays


def employee_month_fund(
    employee: Employee,
    year: int,
    month: int,
    *,
    mid: date,
    cells: dict,
    holiday_map: dict,
) -> dict:
    """Fond zaměstnance za měsíc — součet po dnech dle účinných profilů."""
    days = month_day_list(year, month)
    fund_minutes = 0
    work_days = 0
    holiday_weekdays = 0
    any_continuous = False
    segment_parts: list[tuple[date, date, int]] = []
    seg_start: date | None = None
    seg_weekly: int | None = None
    last_fund_day: date | None = None

    for day in days:
        profile = active_work_time_profile(employee, day)
        if day.weekday() < 5 and day in holiday_map:
            if not (
                profile
                and profile.regime == WorkTimeProfile.Regime.CONTINUOUS
            ):
                holiday_weekdays += 1
        minutes = fund_minutes_for_day(
            employee,
            day,
            cells=cells,
            holiday_map=holiday_map,
            profile=profile,
        )
        if minutes <= 0:
            continue
        work_days += 1
        fund_minutes += minutes
        if profile and profile.regime == WorkTimeProfile.Regime.CONTINUOUS:
            any_continuous = True
        weekly = (
            profile.agreed_weekly_minutes
            if profile and profile.agreed_weekly_minutes
            else minutes * 5
        )
        if seg_start is None:
            seg_start = day
            seg_weekly = weekly
            last_fund_day = day
        elif weekly != seg_weekly:
            segment_parts.append((seg_start, last_fund_day, seg_weekly or 0))
            seg_start = day
            seg_weekly = weekly
            last_fund_day = day
        else:
            last_fund_day = day

    if seg_start is not None and last_fund_day is not None:
        segment_parts.append((seg_start, last_fund_day, seg_weekly or 0))

    segments_label = ""
    if len(segment_parts) > 1:
        bits = []
        for start, end, weekly in segment_parts:
            if start == end:
                date_part = f"{start.day}.{start.month}."
            else:
                date_part = f"{start.day}.–{end.day}.{end.month}."
            bits.append(f"{date_part} {format_hours(weekly)} h/týden")
        segments_label = " · ".join(bits)

    mid_profile = active_work_time_profile(employee, mid)
    _daily, source = resolve_daily_fund_minutes(
        employee, mid, cells=cells, profile=mid_profile
    )
    if len(segment_parts) > 1:
        source = "dynamicky dle profilů úvazku"
    avg_daily = (fund_minutes // work_days) if work_days else _daily
    holiday_daily = (
        daily_minutes_from_profile(mid_profile, employee, mid)
        if mid_profile
        else DEFAULT_DAILY_MINUTES
    )

    return {
        "work_days": work_days,
        "holiday_weekdays": holiday_weekdays,
        "daily_minutes": avg_daily,
        "daily_label": format_hours(avg_daily),
        "fund_minutes": fund_minutes,
        "fund_label": format_hours(fund_minutes),
        "holiday_minutes": holiday_weekdays * holiday_daily,
        "holiday_label": format_hours(holiday_weekdays * holiday_daily),
        "daily_source": source,
        "is_continuous": any_continuous
        or bool(
            mid_profile
            and mid_profile.regime == WorkTimeProfile.Regime.CONTINUOUS
        ),
        "segments_label": segments_label,
    }


def dynamic_balancing_target_minutes(period: BalancingPeriod) -> int:
    """Dynamický cíl: součet denního fondu ve dnech období pod tímto profilem."""
    profile = period.profile
    employee = profile.employment.employee
    total = 0
    day = period.starts_on
    while day <= period.ends_on:
        if profile.covers(day):
            holiday_map = holidays_for_year(day.year)
            if day_is_fund_eligible(
                employee, day, profile, holiday_map, cells=None
            ):
                total += daily_minutes_from_profile(profile, employee, day)
        day += timedelta(days=1)
    return total


def daily_minutes_for_employee(employee: Employee, day: date) -> int:
    """Denní minuty Fondu bez kontextu buněk."""
    daily, _source = resolve_daily_fund_minutes(employee, day, cells=None)
    return daily


def planned_net_minutes_for_employee_month(
    employee: Employee, year: int, month: int
) -> int:
    from datetime import datetime

    from django.utils import timezone

    days = month_day_list(year, month)
    start = timezone.make_aware(
        datetime.combine(days[0], datetime.min.time()),
        timezone.get_current_timezone(),
    )
    end = timezone.make_aware(
        datetime.combine(days[-1] + timedelta(days=1), datetime.min.time()),
        timezone.get_current_timezone(),
    )
    total = 0
    qs = (
        Shift.objects.filter(
            employee=employee,
            status=Shift.Status.PUBLISHED,
            starts_at__lt=end,
            ends_at__gt=start,
        )
        .select_related("shift_type")
    )
    for shift in qs:
        total += shift.planned_net_minutes()
    return total


def planned_net_minutes_in_range(
    employee: Employee, start_day: date, end_day: date
) -> int:
    from datetime import datetime

    from django.utils import timezone

    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(start_day, datetime.min.time()), tz)
    end = timezone.make_aware(
        datetime.combine(end_day + timedelta(days=1), datetime.min.time()), tz
    )
    total = 0
    qs = (
        Shift.objects.filter(
            employee=employee,
            status=Shift.Status.PUBLISHED,
            starts_at__lt=end,
            ends_at__gt=start,
        )
        .select_related("shift_type")
    )
    for shift in qs:
        total += shift.planned_net_minutes()
    return total


def active_balancing_period_for_employee(
    employee: Employee, day: date
) -> BalancingPeriod | None:
    from django.db.models import Q

    employment = employee.current_employment
    if not employment:
        return None
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
    if not profile:
        return None
    return (
        BalancingPeriod.objects.filter(
            profile=profile,
            kind=BalancingPeriod.Kind.SCHEDULE,
            starts_on__lte=day,
            ends_on__gte=day,
        )
        .order_by("-starts_on")
        .first()
    )


def fund_summary_for_employee(employee: Employee, day: date) -> dict | None:
    period = active_balancing_period_for_employee(employee, day)
    if not period:
        return None
    planned = planned_net_minutes_in_range(
        employee, period.starts_on, period.ends_on
    )
    target = dynamic_balancing_target_minutes(period)
    return {
        "period": period,
        "planned_minutes": planned,
        "target_minutes": target,
        "stored_target_minutes": period.target_minutes,
        "planned_label": format_hours(planned),
        "target_label": format_hours(target),
        "delta_minutes": planned - target,
        "delta_label": format_hours(abs(planned - target)),
        "is_short": planned < target,
        "is_over": planned > target,
    }


def balancing_summaries_for_month(
    employee: Employee, year: int, month: int
) -> list[dict]:
    """Všechna vyrovnávací období překrývající měsíc (dynamický cíl)."""
    days = month_day_list(year, month)
    month_start, month_end = days[0], days[-1]
    employment = employee.current_employment
    if not employment:
        return []
    periods = (
        BalancingPeriod.objects.filter(
            profile__employment=employment,
            profile__is_active=True,
            kind=BalancingPeriod.Kind.SCHEDULE,
            starts_on__lte=month_end,
            ends_on__gte=month_start,
        )
        .select_related("profile")
        .order_by("starts_on")
    )
    summaries = []
    for period in periods:
        planned = planned_net_minutes_in_range(
            employee, period.starts_on, period.ends_on
        )
        target = dynamic_balancing_target_minutes(period)
        delta = planned - target
        summaries.append(
            {
                "period": period,
                "planned_minutes": planned,
                "target_minutes": target,
                "planned_label": format_hours(planned),
                "target_label": format_hours(target),
                "delta_minutes": delta,
                "delta_label": format_hours(abs(delta)),
                "is_short": delta < 0,
                "is_over": delta > 0,
                "label": (
                    f"{period.starts_on:%d.%m.}–{period.ends_on:%d.%m.} "
                    f"{format_hours(planned)}/{format_hours(target)} h"
                ),
            }
        )
    return summaries
