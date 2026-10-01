"""Denní rozvrh činností: mřížka, preference, generátor.

Rozhraní je připravené na další typy činností / požadavky bez přepisu matice:
slot = ActivityItem (lokalita + typ + poznámka + čas); preference nese váhy
a volitelný výchozí typ.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from apps.employees.models import Employee
from apps.employees.services import employment_for_day
from apps.shifts.models import Shift, ShiftType
from apps.shifts.services import employees_visible_for_shift_plan
from apps.workplaces.models import Workplace

from .models import (
    ActivityItem,
    ActivityLocation,
    ActivityPreference,
    ActivityType,
)
from .services import (
    ActivityConflictError,
    _audit,
    create_activity_item,
    delete_activity_item,
    hour_items_for_day,
    items_for_day,
    published_work_shifts_for_day,
)


def default_activity_type() -> ActivityType | None:
    return (
        ActivityType.objects.filter(is_active=True, code="kontrola").first()
        or ActivityType.objects.filter(is_active=True)
        .order_by("sort_order", "name")
        .first()
    )


def preferences_for_employee(employee: Employee) -> list[ActivityPreference]:
    return list(
        ActivityPreference.objects.filter(employee=employee)
        .select_related("location", "location__parent", "default_activity_type")
        .order_by("sort_order", "id")
    )


@transaction.atomic
def save_preferences(
    *,
    user: AbstractBaseUser,
    employee: Employee,
    rows: list[dict],
) -> list[ActivityPreference]:
    """rows: [{location_id, frequency, sort_order, default_activity_type_id|None}, …]"""
    kept_ids: list[int] = []
    result: list[ActivityPreference] = []
    seen_locations: set[int] = set()
    for index, row in enumerate(rows):
        loc_id = row.get("location_id")
        if not loc_id:
            continue
        loc_id = int(loc_id)
        if loc_id in seen_locations:
            raise ActivityConflictError("Každou lokalitu lze v preferencích jen jednou.")
        seen_locations.add(loc_id)
        location = ActivityLocation.objects.filter(pk=loc_id, is_active=True).first()
        if location is None:
            raise ActivityConflictError("Neplatná lokalita v preferencích.")
        freq = int(row.get("frequency") or 1)
        if freq < 1:
            raise ActivityConflictError("Četnost musí být alespoň 1.")
        type_id = row.get("default_activity_type_id")
        act_type = None
        if type_id:
            act_type = ActivityType.objects.filter(pk=type_id, is_active=True).first()
        pref, _created = ActivityPreference.objects.update_or_create(
            employee=employee,
            location=location,
            defaults={
                "frequency": freq,
                "sort_order": int(row.get("sort_order") or (index + 1) * 10),
                "default_activity_type": act_type,
            },
        )
        kept_ids.append(pref.pk)
        result.append(pref)
    ActivityPreference.objects.filter(employee=employee).exclude(
        pk__in=kept_ids
    ).delete()
    _audit(
        user,
        "activity_preference.save",
        "Employee",
        employee.pk,
        f"prefs={len(result)}",
    )
    return result


def allocate_hours_by_weights(total_hours: int, weights: list[int]) -> list[int]:
    """Metoda největších zbytků — součet alokací = total_hours."""
    if total_hours <= 0 or not weights:
        return [0] * len(weights)
    weight_sum = sum(weights)
    if weight_sum <= 0:
        return [0] * len(weights)
    raw = [w * total_hours / weight_sum for w in weights]
    floors = [int(r) for r in raw]
    leftover = total_hours - sum(floors)
    order = sorted(
        range(len(weights)),
        key=lambda i: (raw[i] - floors[i], -i),
        reverse=True,
    )
    for i in order:
        if leftover <= 0:
            break
        floors[i] += 1
        leftover -= 1
    return floors


def _hour_slots_for_shift(shift: Shift) -> list[tuple[datetime, datetime]]:
    """Seznam intervalů [start, end) pokrývajících směnu po hodinách."""
    start = timezone.localtime(shift.starts_at)
    end = timezone.localtime(shift.ends_at)
    if end <= start:
        return []
    slots: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        next_hour = cursor.replace(minute=0, second=0, microsecond=0) + timedelta(
            hours=1
        )
        slot_end = min(next_hour, end)
        if slot_end > cursor:
            slots.append((cursor, slot_end))
        cursor = slot_end
    return slots


def _merge_location_blocks(
    slots: list[tuple[datetime, datetime]],
    location_ids: list[int],
) -> list[tuple[int, datetime, datetime]]:
    """Sloučí sousední sloty se stejnou lokalitou."""
    if not slots or len(slots) != len(location_ids):
        return []
    blocks: list[tuple[int, datetime, datetime]] = []
    cur_loc = location_ids[0]
    cur_start = slots[0][0]
    cur_end = slots[0][1]
    for (s, e), loc_id in zip(slots[1:], location_ids[1:]):
        if loc_id == cur_loc and s == cur_end:
            cur_end = e
        else:
            blocks.append((cur_loc, cur_start, cur_end))
            cur_loc = loc_id
            cur_start = s
            cur_end = e
    blocks.append((cur_loc, cur_start, cur_end))
    return blocks


@transaction.atomic
def generate_day_plan(
    *,
    user: AbstractBaseUser,
    employee: Employee,
    day: date,
    replace_existing: bool = False,
) -> list[ActivityItem]:
    """Vygeneruje ActivityItem podle preferencí a publikované směny práce."""
    shifts = published_work_shifts_for_day(employee, day)
    if not shifts:
        raise ActivityConflictError(
            "Bez publikované směny práce nelze generovat plán."
        )
    prefs = preferences_for_employee(employee)
    if not prefs:
        raise ActivityConflictError(
            "Nejdříve nastavte preferované lokality a četnosti."
        )
    existing = hour_items_for_day(employee, day)
    if existing and not replace_existing:
        raise ActivityConflictError(
            "Pro tento den už činnosti existují. Potvrďte přepsání."
        )
    for item in existing:
        delete_activity_item(user=user, item=item)

    fallback_type = default_activity_type()
    if fallback_type is None:
        raise ActivityConflictError("Chybí aktivní typ činnosti v číselníku.")

    created: list[ActivityItem] = []
    order = 10
    for shift in shifts:
        slots = _hour_slots_for_shift(shift)
        if not slots:
            continue
        weights = [p.frequency for p in prefs]
        counts = allocate_hours_by_weights(len(slots), weights)
        location_ids: list[int] = []
        type_by_loc: dict[int, ActivityType] = {}
        for pref, count in zip(prefs, counts):
            location_ids.extend([pref.location_id] * count)
            type_by_loc[pref.location_id] = (
                pref.default_activity_type or fallback_type
            )
        # pokud kvůli zaokrouhlení něco chybí (nemělo), doplň první preferenci
        while len(location_ids) < len(slots):
            location_ids.append(prefs[0].location_id)
        location_ids = location_ids[: len(slots)]
        blocks = _merge_location_blocks(slots, location_ids)
        for loc_id, starts, ends in blocks:
            loc = ActivityLocation.objects.get(pk=loc_id)
            act_type = type_by_loc.get(loc_id) or fallback_type
            item = create_activity_item(
                user=user,
                employee=employee,
                shift=shift,
                location=loc,
                activity_type=act_type,
                starts_at=starts,
                ends_at=ends,
                note="",
                sort_order=order,
                all_day=False,
            )
            created.append(item)
            order += 10
    _audit(
        user,
        "activity.generate",
        "Employee",
        employee.pk,
        f"day={day.isoformat()}; items={len(created)}",
    )
    return created


@transaction.atomic
def clear_day_plan(
    *, user: AbstractBaseUser, employee: Employee, day: date
) -> int:
    items = items_for_day(employee, day)
    count = len(items)
    for item in items:
        delete_activity_item(user=user, item=item)
    _audit(
        user,
        "activity.clear_day",
        "Employee",
        employee.pk,
        f"day={day.isoformat()}; deleted={count}",
    )
    return count


@dataclass
class HourColumn:
    label: str
    start: datetime
    end: datetime


def hour_range_label(start: datetime, end: datetime) -> str:
    """Kompaktní popisek úseku, např. 8–9 nebo 14–14:30."""
    def _hm(dt: datetime, *, force_minutes: bool = False) -> str:
        if force_minutes or dt.minute or dt.second:
            return f"{dt.hour}:{dt.minute:02d}"
        return str(dt.hour)

    end_needs_min = bool(end.minute or end.second) or (
        end.hour == start.hour and end > start
    )
    return f"{_hm(start)}–{_hm(end, force_minutes=end_needs_min)}"


@dataclass
class BoardCell:
    hour_index: int
    in_shift: bool
    items: list[ActivityItem]
    slot_start: datetime | None = None
    slot_end: datetime | None = None
    label: str = ""


@dataclass
class BoardRow:
    employee: Employee
    shifts: list[Shift]
    cells: list[BoardCell]


def _is_work_shift(shift: Shift) -> bool:
    if not shift.shift_type_id:
        return True
    st = shift.shift_type
    return st.kind == ShiftType.Kind.WORK and st.counts_as_work


def employees_for_workplace_day(
    user: AbstractBaseUser, day: date, workplace: Workplace
) -> list[Employee]:
    visible = employees_visible_for_shift_plan(user)
    visible_ids = list(visible.values_list("pk", flat=True))
    if not visible_ids:
        return []
    tz = timezone.get_current_timezone()
    range_start = timezone.make_aware(datetime.combine(day, time.min), tz)
    range_end = timezone.make_aware(
        datetime.combine(day + timedelta(days=1), time.min), tz
    )
    shifts = (
        Shift.objects.filter(
            employee_id__in=visible_ids,
            workplace=workplace,
            status=Shift.Status.PUBLISHED,
            starts_at__gte=range_start,
            starts_at__lt=range_end,
        )
        .select_related("shift_type", "employee")
        .order_by("starts_at")
    )
    eligible: dict[int, Employee] = {}
    for shift in shifts:
        if not _is_work_shift(shift):
            continue
        if employment_for_day(shift.employee, day) is None:
            continue
        eligible[shift.employee_id] = shift.employee
    return sorted(
        eligible.values(),
        key=lambda e: (e.last_name, e.first_name, e.pk),
    )


def build_workplace_board(
    *,
    user: AbstractBaseUser,
    day: date,
    workplace: Workplace,
) -> tuple[list[HourColumn], list[BoardRow]]:
    employees = employees_for_workplace_day(user, day, workplace)
    if not employees:
        return [], []

    all_shifts: list[Shift] = []
    shifts_by_emp: dict[int, list[Shift]] = {}
    for emp in employees:
        sh = [
            s
            for s in published_work_shifts_for_day(emp, day)
            if s.workplace_id == workplace.pk
        ]
        shifts_by_emp[emp.pk] = sh
        all_shifts.extend(sh)
    if not all_shifts:
        return [], []

    min_start = min(timezone.localtime(s.starts_at) for s in all_shifts)
    max_end = max(timezone.localtime(s.ends_at) for s in all_shifts)
    # zarovnání na celé hodiny
    col_start = min_start.replace(minute=0, second=0, microsecond=0)
    columns: list[HourColumn] = []
    cursor = col_start
    while cursor < max_end:
        nxt = cursor + timedelta(hours=1)
        col_end = min(nxt, max_end) if nxt > max_end else nxt
        columns.append(
            HourColumn(
                label=hour_range_label(cursor, col_end),
                start=cursor,
                end=col_end,
            )
        )
        cursor = nxt
        if len(columns) > 24:
            break

    items_by_emp: dict[int, list[ActivityItem]] = {}
    for emp in employees:
        items_by_emp[emp.pk] = hour_items_for_day(emp, day)

    rows: list[BoardRow] = []
    for emp in employees:
        shifts = shifts_by_emp.get(emp.pk, [])
        cells: list[BoardCell] = []
        for idx, col in enumerate(columns):
            in_shift = any(
                timezone.localtime(s.starts_at) < col.end
                and timezone.localtime(s.ends_at) > col.start
                for s in shifts
            )
            overlapping = [
                it
                for it in items_by_emp.get(emp.pk, [])
                if timezone.localtime(it.starts_at) < col.end
                and timezone.localtime(it.ends_at) > col.start
            ]
            slot_start = col.start if in_shift else None
            slot_end = col.end if in_shift else None
            if in_shift and shifts:
                # ořez na skutečnou směnu
                for s in shifts:
                    s0 = timezone.localtime(s.starts_at)
                    s1 = timezone.localtime(s.ends_at)
                    if s0 < col.end and s1 > col.start:
                        slot_start = max(col.start, s0)
                        slot_end = min(col.end, s1)
                        break
            cells.append(
                BoardCell(
                    hour_index=idx,
                    in_shift=in_shift,
                    items=overlapping,
                    slot_start=slot_start,
                    slot_end=slot_end,
                    label=(
                        hour_range_label(slot_start, slot_end)
                        if slot_start and slot_end
                        else ""
                    ),
                )
            )
        rows.append(BoardRow(employee=emp, shifts=shifts, cells=cells))
    return columns, rows


def find_shift_covering(
    employee: Employee, day: date, starts_at: datetime, ends_at: datetime
) -> Shift | None:
    for shift in published_work_shifts_for_day(employee, day):
        if starts_at >= shift.starts_at and ends_at <= shift.ends_at:
            return shift
    return None


def items_overlapping_interval(
    employee: Employee, day: date, starts_at, ends_at
) -> list[ActivityItem]:
    return [
        it
        for it in hour_items_for_day(employee, day)
        if it.starts_at < ends_at and it.ends_at > starts_at
    ]


def _resolve_row_interval(slot_start, slot_end, time_from, time_to):
    """Vrátí (starts, ends) uvnitř slotu; prázdné časy = celý slot."""
    local_start = timezone.localtime(slot_start).replace(second=0, microsecond=0)
    local_end = timezone.localtime(slot_end).replace(second=0, microsecond=0)
    start = local_start
    end = local_end
    if time_from is not None:
        start = local_start.replace(
            hour=time_from.hour,
            minute=time_from.minute,
            second=0,
            microsecond=0,
        )
    if time_to is not None:
        end = local_start.replace(
            hour=time_to.hour,
            minute=time_to.minute,
            second=0,
            microsecond=0,
        )
        # Konec slotu může být na další hodině (např. 09:00) — použij konec slotu
        if time_to.hour == local_end.hour and time_to.minute == local_end.minute:
            end = local_end
    if start < local_start or end > local_end or end <= start:
        raise ActivityConflictError(
            "Časy Od–Do musí ležet uvnitř hodinového úseku "
            f"({local_start:%H:%M}–{local_end:%H:%M})."
        )
    return start, end


@transaction.atomic
def replace_slot_items(
    *,
    user: AbstractBaseUser,
    employee: Employee,
    day: date,
    starts_at,
    ends_at,
    rows: list[dict],
) -> list[ActivityItem]:
    """Nahradí hodinové činnosti v daném intervalu sadou řádků (0–10).

    rows: [{location|None, activity_type, note, time_from|None, time_to|None}, …]
    """
    if len(rows) > 10:
        raise ActivityConflictError("V jedné hodině lze mít nejvýše 10 činností.")
    # Směna musí pokrývat alespoň hodinový slot
    shift = find_shift_covering(employee, day, starts_at, ends_at)
    if shift is None:
        # zkus pokrýt střed slotu (pro ořezané intervaly)
        mid = starts_at + (ends_at - starts_at) / 2
        shift = find_shift_covering(employee, day, mid, mid + timedelta(minutes=1))
    if shift is None:
        raise ActivityConflictError("Čas není uvnitř publikované směny.")
    for existing in items_overlapping_interval(employee, day, starts_at, ends_at):
        delete_activity_item(user=user, item=existing)
    created: list[ActivityItem] = []
    order = 10
    for row in rows:
        act_type = row.get("activity_type")
        if act_type is None:
            continue
        item_start, item_end = _resolve_row_interval(
            starts_at,
            ends_at,
            row.get("time_from"),
            row.get("time_to"),
        )
        # find_shift for actual item interval
        item_shift = find_shift_covering(employee, day, item_start, item_end) or shift
        item = create_activity_item(
            user=user,
            employee=employee,
            shift=item_shift,
            location=row.get("location"),
            activity_type=act_type,
            starts_at=item_start,
            ends_at=item_end,
            note=row.get("note") or "",
            sort_order=order,
            all_day=False,
            vehicle=row.get("vehicle"),
        )
        created.append(item)
        order += 10
    return created


def day_span_for_shifts(shifts: list[Shift]) -> tuple[datetime, datetime] | None:
    if not shifts:
        return None
    return (
        min(s.starts_at for s in shifts),
        max(s.ends_at for s in shifts),
    )


@transaction.atomic
def create_day_task(
    *,
    user: AbstractBaseUser,
    employee: Employee,
    day: date,
    location: ActivityLocation | None,
    activity_type: ActivityType,
    note: str = "",
    vehicle=None,
) -> ActivityItem:
    shifts = published_work_shifts_for_day(employee, day)
    span = day_span_for_shifts(shifts)
    if span is None:
        raise ActivityConflictError(
            "Bez publikované směny práce nelze přidat denní úkol."
        )
    starts, ends = span
    return create_activity_item(
        user=user,
        employee=employee,
        shift=shifts[0],
        location=location,
        activity_type=activity_type,
        starts_at=starts,
        ends_at=ends,
        note=note or "",
        sort_order=5,
        all_day=True,
        vehicle=vehicle,
    )


def build_employee_hour_axis(
    employee: Employee, day: date
) -> tuple[list[Shift], list[BoardCell], list[ActivityItem]]:
    shifts = published_work_shifts_for_day(employee, day)
    items = hour_items_for_day(employee, day)
    cells: list[BoardCell] = []
    idx = 0
    for shift in shifts:
        for start, end in _hour_slots_for_shift(shift):
            overlapping = [
                it
                for it in items
                if timezone.localtime(it.starts_at) < end
                and timezone.localtime(it.ends_at) > start
            ]
            cells.append(
                BoardCell(
                    hour_index=idx,
                    in_shift=True,
                    items=overlapping,
                    slot_start=start,
                    slot_end=end,
                    label=hour_range_label(start, end),
                )
            )
            idx += 1
    return shifts, cells, items
