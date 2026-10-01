"""Views plánu činností."""

from __future__ import annotations

from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.forms import formset_factory
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.employees.models import Employee
from apps.workplaces.models import Workplace

from .calendar_month import build_activity_month_calendar
from .day_roster import (
    work_shifts_roster_for_day,
    workplace_shift_counts_for_day,
)
from .export_pack import build_activity_export_pack
from .export_xlsx import build_activity_workbook
from .forms import (
    ActivityItemForm,
    ActivityLocationForm,
    DayPlanFilterForm,
    DayTaskForm,
    PreferenceRowForm,
    SLOT_MAX_ITEMS,
    SlotMetaForm,
    SlotRowForm,
)
from .models import ActivityItem, ActivityLocation, ActivityType, next_location_color
from .schedule import (
    build_employee_hour_axis,
    build_workplace_board,
    clear_day_plan,
    create_day_task,
    default_activity_type,
    employees_for_workplace_day,
    generate_day_plan,
    items_overlapping_interval,
    preferences_for_employee,
    replace_slot_items,
    save_preferences,
)
from .services import (
    ActivityConflictError,
    can_export_activity_plan,
    can_manage_activities,
    can_plan_activity_for_day,
    create_activity_item,
    day_tasks_for_day,
    delete_activity_item,
    employees_for_activity_day,
    locations_geojson_collection,
    locations_grouped_for_list,
    map_cities_active,
    published_work_shifts_for_day,
    resolve_map_city,
    save_activity_location,
    update_activity_item,
)


def _require_manager(user):
    if not can_manage_activities(user):
        raise PermissionDenied


def _require_export(user):
    _require_manager(user)
    if not can_export_activity_plan(user):
        raise PermissionDenied


def _parse_day(raw) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None


def _local_dt_for_input(dt):
    if dt is None:
        return None
    local = timezone.localtime(dt)
    return local.replace(second=0, microsecond=0)


def _iso_local(dt) -> str:
    if dt is None:
        return ""
    return timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M")


def _time_hm(dt):
    local = timezone.localtime(dt).replace(second=0, microsecond=0)
    return local.time().replace(second=0, microsecond=0)


def _slot_item_times(item: ActivityItem):
    """Vždy explicitní Od–Do položky (HH:mm)."""
    return _time_hm(item.starts_at), _time_hm(item.ends_at)


def _day_plan_url(
    day: date,
    *,
    workplace_id: int | None = None,
    employee_id: int | None = None,
) -> str:
    url = f"{reverse('activity_day')}?day={day.isoformat()}"
    if workplace_id:
        url += f"&workplace={workplace_id}"
    if employee_id:
        url += f"&employee={employee_id}"
    return url


def _wants_json(request) -> bool:
    accept = request.headers.get("Accept", "")
    return "application/json" in accept


@login_required
@require_http_methods(["GET"])
def activity_day(request):
    """Přehled směn dne, deska pracoviště × hodiny, detail zaměstnance."""
    _require_manager(request.user)
    today = timezone.localdate()
    day = _parse_day(request.GET.get("day")) or today
    workplaces = Workplace.objects.filter(is_active=True).order_by("name")
    workplace = None
    wp_raw = request.GET.get("workplace")
    if wp_raw:
        workplace = workplaces.filter(pk=wp_raw).first()
    # Bez auto-výběru prvního WP — výchozí je přehled směn dne.

    day_roster = work_shifts_roster_for_day(request.user, day)
    workplace_counts = workplace_shift_counts_for_day(request.user, day)
    other_workplaces_with_shifts = [
        {"workplace": wp, "count": workplace_counts[wp.pk]}
        for wp in workplaces
        if wp.pk in workplace_counts
        and (workplace is None or wp.pk != workplace.pk)
    ]

    employees = (
        employees_for_activity_day(request.user, day)
        if workplace is None
        else Employee.objects.filter(
            pk__in=[
                e.pk
                for e in employees_for_workplace_day(
                    request.user, day, workplace
                )
            ]
        ).order_by("last_name", "first_name")
    )
    filter_data = request.GET.copy()
    if not filter_data.get("day"):
        filter_data["day"] = day.isoformat()
    filter_form = DayPlanFilterForm(
        filter_data,
        employee_queryset=employees_for_activity_day(request.user, day),
        workplace_queryset=workplaces,
        workplace_counts=workplace_counts,
    )

    columns = []
    rows = []
    employees_empty = False
    if workplace is not None:
        columns, rows = build_workplace_board(
            user=request.user, day=day, workplace=workplace
        )
        employees_empty = len(rows) == 0

    employee = None
    emp_cells = []
    shifts = []
    items = []
    emp_day_tasks = []
    board_day_tasks = []
    emp_raw = request.GET.get("employee")
    if emp_raw:
        employee = get_object_or_404(Employee, pk=emp_raw)
        if not can_plan_activity_for_day(request.user, employee, day):
            messages.warning(
                request,
                "Zaměstnanec nemá v tento den publikovanou směnu práce "
                "nebo aktivní pracovní vztah.",
            )
            employee = None
        else:
            shifts, emp_cells, items = build_employee_hour_axis(employee, day)
            emp_day_tasks = day_tasks_for_day(employee, day)

    if workplace is not None and rows:
        for row in rows:
            tasks = day_tasks_for_day(row.employee, day)
            if tasks:
                board_day_tasks.append(
                    {"employee": row.employee, "tasks": tasks}
                )

    month_cal = build_activity_month_calendar(
        user=request.user,
        selected=day,
        workplace=workplace,
        employee=employee,
    )

    if rows:
        export_employees = [row.employee for row in rows]
    elif employee is not None:
        export_employees = [employee]
    else:
        export_employees = []

    show_day_roster = workplace is None and employee is None

    return render(
        request,
        "activities/day.html",
        {
            "title": "Činnost – plán dne",
            "filter_form": filter_form,
            "day": day,
            "workplace": workplace,
            "columns": columns,
            "rows": rows,
            "employees_empty": employees_empty and workplace is not None,
            "other_workplaces_with_shifts": other_workplaces_with_shifts,
            "day_roster": day_roster,
            "show_day_roster": show_day_roster,
            "employee": employee,
            "emp_cells": emp_cells,
            "shifts": shifts,
            "items": items,
            "emp_day_tasks": emp_day_tasks,
            "board_day_tasks": board_day_tasks,
            "month_cal": month_cal,
            "export_employees": export_employees,
            "can_export_employee": bool(
                can_export_activity_plan(request.user)
                and employee
                and day
                and shifts
            ),
            "can_export_workplace": bool(
                can_export_activity_plan(request.user) and workplace and rows
            ),
            "slot_form_url": reverse("activity_slot_form"),
            "day_task_form_url": reverse("activity_day_task_form"),
            "prefs_url": (
                reverse("activity_preferences", args=[employee.pk])
                if employee
                else ""
            ),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def activity_preferences(request, employee_id: int):
    _require_manager(request.user)
    employee = get_object_or_404(Employee, pk=employee_id)
    day = _parse_day(request.GET.get("day")) or timezone.localdate()
    PrefFormSet = formset_factory(
        PreferenceRowForm, extra=1, max_num=20, can_delete=True
    )
    existing = preferences_for_employee(employee)
    if request.method == "POST":
        formset = PrefFormSet(request.POST, prefix="pref")
        if formset.is_valid():
            rows = []
            for form in formset:
                if form.cleaned_data.get("DELETE"):
                    continue
                loc = form.cleaned_data.get("location")
                if not loc:
                    continue
                rows.append(
                    {
                        "location_id": loc.pk,
                        "frequency": form.cleaned_data.get("frequency") or 1,
                        "sort_order": form.cleaned_data.get("sort_order") or 100,
                        "default_activity_type_id": (
                            form.cleaned_data["default_activity_type"].pk
                            if form.cleaned_data.get("default_activity_type")
                            else None
                        ),
                    }
                )
            try:
                save_preferences(
                    user=request.user, employee=employee, rows=rows
                )
                messages.success(request, "Šablona lokalit byla uložena.")
                return redirect(
                    _day_plan_url(day, employee_id=employee.pk)
                    + (
                        f"&workplace={request.GET.get('workplace')}"
                        if request.GET.get("workplace")
                        else ""
                    )
                )
            except ActivityConflictError as exc:
                messages.error(request, "; ".join(exc.messages))
        else:
            messages.error(request, "Opravte chyby ve formuláři šablony lokalit.")
    else:
        initial = [
            {
                "location": p.location_id,
                "frequency": p.frequency,
                "sort_order": p.sort_order,
                "default_activity_type": p.default_activity_type_id,
            }
            for p in existing
        ]
        formset = PrefFormSet(initial=initial, prefix="pref")
    return render(
        request,
        "activities/preferences.html",
        {
            "title": f"Šablona lokalit · {employee}",
            "employee": employee,
            "day": day,
            "formset": formset,
            "workplace_id": request.GET.get("workplace") or "",
        },
    )


@login_required
@require_http_methods(["POST"])
def activity_generate(request):
    _require_manager(request.user)
    employee = get_object_or_404(Employee, pk=request.POST.get("employee"))
    day = _parse_day(request.POST.get("day"))
    workplace_id = request.POST.get("workplace") or None
    replace = request.POST.get("replace") in ("1", "on", "true", "yes")
    if day is None:
        messages.error(request, "Neplatný den.")
        return redirect("activity_day")
    if not can_plan_activity_for_day(request.user, employee, day):
        messages.error(request, "Nelze generovat: chybí směna nebo vztah.")
        return HttpResponseRedirect(
            _day_plan_url(
                day,
                workplace_id=int(workplace_id) if workplace_id else None,
                employee_id=employee.pk,
            )
        )
    try:
        created = generate_day_plan(
            user=request.user,
            employee=employee,
            day=day,
            replace_existing=replace,
        )
        messages.success(
            request, f"Vygenerováno {len(created)} bloků činnosti."
        )
    except ActivityConflictError as exc:
        messages.error(request, "; ".join(exc.messages))
    return HttpResponseRedirect(
        _day_plan_url(
            day,
            workplace_id=int(workplace_id) if workplace_id else None,
            employee_id=employee.pk,
        )
    )


@login_required
@require_http_methods(["POST"])
def activity_clear_day(request):
    _require_manager(request.user)
    employee = get_object_or_404(Employee, pk=request.POST.get("employee"))
    day = _parse_day(request.POST.get("day"))
    workplace_id = request.POST.get("workplace") or None
    if day is None:
        messages.error(request, "Neplatný den.")
        return redirect("activity_day")
    n = clear_day_plan(user=request.user, employee=employee, day=day)
    messages.success(request, f"Smazáno {n} položek.")
    return HttpResponseRedirect(
        _day_plan_url(
            day,
            workplace_id=int(workplace_id) if workplace_id else None,
            employee_id=employee.pk,
        )
    )


@login_required
@require_http_methods(["GET"])
def activity_slot_form(request):
    """Tělo modalu — až 10 činností v hodinové buňce."""
    _require_manager(request.user)
    employee = get_object_or_404(Employee, pk=request.GET.get("employee"))
    day = _parse_day(request.GET.get("day"))
    if day is None:
        return JsonResponse({"ok": False, "error": "Neplatný den."}, status=400)
    starts_raw = request.GET.get("starts_at") or ""
    ends_raw = request.GET.get("ends_at") or ""
    meta = SlotMetaForm({"starts_at": starts_raw, "ends_at": ends_raw})
    if not meta.is_valid():
        return JsonResponse({"ok": False, "error": "Neplatný interval."}, status=400)
    starts = meta.cleaned_data["starts_at"]
    ends = meta.cleaned_data["ends_at"]
    existing = items_overlapping_interval(employee, day, starts, ends)[
        :SLOT_MAX_ITEMS
    ]
    RowFormSet = formset_factory(
        SlotRowForm, extra=0, max_num=SLOT_MAX_ITEMS, absolute_max=SLOT_MAX_ITEMS
    )
    slot_from = _time_hm(starts)
    slot_to = _time_hm(ends)
    initial_rows = []
    for it in existing:
        t_from, t_to = _slot_item_times(it)
        initial_rows.append(
            {
                "item_id": it.pk,
                "location": it.location_id,
                "activity_type": it.activity_type_id,
                "vehicle": it.vehicle_id,
                "note": it.note,
                "time_from": t_from,
                "time_to": t_to,
            }
        )
    if not initial_rows:
        def_type = default_activity_type()
        initial_rows = [
            {
                "activity_type": def_type.pk if def_type else None,
                "time_from": slot_from,
                "time_to": slot_to,
            }
        ]
    formset = RowFormSet(initial=initial_rows, prefix="slot")
    meta_form = SlotMetaForm(
        initial={"starts_at": _iso_local(starts), "ends_at": _iso_local(ends)}
    )
    return render(
        request,
        "activities/_slot_dialog_body.html",
        {
            "formset": formset,
            "meta_form": meta_form,
            "employee": employee,
            "day": day,
            "slot_max": SLOT_MAX_ITEMS,
            "items_count": len(existing),
            "slot_label": (
                f"{timezone.localtime(starts):%H:%M}–"
                f"{timezone.localtime(ends):%H:%M}"
            ),
            "slot_start_hm": slot_from.strftime("%H:%M"),
            "slot_end_hm": slot_to.strftime("%H:%M"),
        },
    )


@login_required
@require_http_methods(["POST"])
def activity_slot_save(request):
    _require_manager(request.user)
    employee = get_object_or_404(Employee, pk=request.POST.get("employee"))
    day = _parse_day(request.POST.get("day"))
    if day is None:
        return JsonResponse({"ok": False, "error": "Neplatný den."}, status=400)
    if not can_plan_activity_for_day(request.user, employee, day):
        return JsonResponse(
            {"ok": False, "error": "Nelze plánovat pro tohoto zaměstnance."},
            status=400,
        )

    # Smazání jedné položky
    if request.POST.get("delete") == "1":
        item_id = request.POST.get("item_id")
        item = get_object_or_404(ActivityItem, pk=item_id, employee=employee)
        delete_activity_item(user=request.user, item=item)
        return JsonResponse({"ok": True, "deleted": 1})

    meta = SlotMetaForm(request.POST)
    RowFormSet = formset_factory(
        SlotRowForm, extra=0, max_num=SLOT_MAX_ITEMS, absolute_max=SLOT_MAX_ITEMS
    )
    formset = RowFormSet(request.POST, prefix="slot")
    if not meta.is_valid() or not formset.is_valid():
        return JsonResponse(
            {
                "ok": False,
                "error": "Opravte formulář.",
                "errors": {
                    "meta": meta.errors,
                    "rows": formset.errors,
                    "non_form": formset.non_form_errors(),
                },
            },
            status=400,
        )
    starts = meta.cleaned_data["starts_at"]
    ends = meta.cleaned_data["ends_at"]
    rows = []
    for form in formset:
        cd = form.cleaned_data
        if not cd:
            continue
        if not cd.get("activity_type") and not cd.get("location") and not cd.get(
            "vehicle"
        ) and not (cd.get("note") or "").strip():
            continue
        if not cd.get("activity_type"):
            return JsonResponse(
                {"ok": False, "error": "Každý vyplněný řádek musí mít typ činnosti."},
                status=400,
            )
        rows.append(
            {
                "location": cd.get("location"),
                "activity_type": cd["activity_type"],
                "vehicle": cd.get("vehicle"),
                "note": cd.get("note") or "",
                "time_from": cd.get("time_from"),
                "time_to": cd.get("time_to"),
            }
        )
    if len(rows) > SLOT_MAX_ITEMS:
        return JsonResponse(
            {
                "ok": False,
                "error": f"V jedné hodině lze mít nejvýše {SLOT_MAX_ITEMS} činností.",
            },
            status=400,
        )
    try:
        created = replace_slot_items(
            user=request.user,
            employee=employee,
            day=day,
            starts_at=starts,
            ends_at=ends,
            rows=rows,
        )
    except ActivityConflictError as exc:
        return JsonResponse(
            {"ok": False, "error": "; ".join(exc.messages)}, status=400
        )
    return JsonResponse({"ok": True, "count": len(created)})


@login_required
@require_http_methods(["GET"])
def activity_day_task_form(request):
    """Modal denního úkolu (mimo hodinovou mřížku)."""
    _require_manager(request.user)
    employee = get_object_or_404(Employee, pk=request.GET.get("employee"))
    day = _parse_day(request.GET.get("day"))
    if day is None:
        return JsonResponse({"ok": False, "error": "Neplatný den."}, status=400)
    form = DayTaskForm(
        initial={
            "activity_type": (
                default_activity_type().pk if default_activity_type() else None
            )
        }
    )
    return render(
        request,
        "activities/_day_task_dialog_body.html",
        {
            "form": form,
            "employee": employee,
            "day": day,
            "workplace_id": request.GET.get("workplace") or "",
        },
    )


@login_required
@require_http_methods(["POST"])
def activity_day_task_save(request):
    _require_manager(request.user)
    employee = get_object_or_404(Employee, pk=request.POST.get("employee"))
    day = _parse_day(request.POST.get("day"))
    workplace_id = request.POST.get("workplace") or None
    if day is None:
        return JsonResponse({"ok": False, "error": "Neplatný den."}, status=400)
    if not can_plan_activity_for_day(request.user, employee, day):
        return JsonResponse(
            {"ok": False, "error": "Nelze plánovat pro tohoto zaměstnance."},
            status=400,
        )
    form = DayTaskForm(request.POST)
    if not form.is_valid():
        return JsonResponse(
            {"ok": False, "error": "Opravte formulář.", "errors": form.errors},
            status=400,
        )
    try:
        item = create_day_task(
            user=request.user,
            employee=employee,
            day=day,
            location=form.cleaned_data.get("location"),
            activity_type=form.cleaned_data["activity_type"],
            note=form.cleaned_data.get("note") or "",
            vehicle=form.cleaned_data.get("vehicle"),
        )
    except ActivityConflictError as exc:
        return JsonResponse(
            {"ok": False, "error": "; ".join(exc.messages)}, status=400
        )
    return JsonResponse({"ok": True, "id": item.pk, "workplace": workplace_id})


@login_required
@require_http_methods(["POST"])
def activity_item_create(request):
    _require_manager(request.user)
    emp_id = request.POST.get("employee")
    day = _parse_day(request.POST.get("day"))
    employee = get_object_or_404(Employee, pk=emp_id)
    if day is None:
        messages.error(request, "Neplatný den.")
        return redirect("activity_day")
    if not can_plan_activity_for_day(request.user, employee, day):
        messages.error(
            request,
            "Zaměstnanec nemá v tento den publikovanou směnu práce "
            "nebo aktivní pracovní vztah.",
        )
        return redirect("activity_day")
    shifts = published_work_shifts_for_day(employee, day)
    form = ActivityItemForm(
        request.POST, employee=employee, day=day, shifts=shifts
    )
    if not form.is_valid():
        messages.error(request, "Opravte chyby ve formuláři činnosti.")
        return HttpResponseRedirect(
            _day_plan_url(day, employee_id=employee.pk)
        )
    try:
        create_activity_item(
            user=request.user,
            employee=employee,
            shift=form.cleaned_data["shift"],
            location=form.cleaned_data["location"],
            activity_type=form.cleaned_data["activity_type"],
            starts_at=form.cleaned_data["starts_at"],
            ends_at=form.cleaned_data["ends_at"],
            note=form.cleaned_data.get("note") or "",
            sort_order=form.cleaned_data.get("sort_order") or 100,
            vehicle=form.cleaned_data.get("vehicle"),
        )
        messages.success(request, "Činnost byla přidána.")
    except ActivityConflictError as exc:
        messages.error(request, "; ".join(exc.messages))
    return HttpResponseRedirect(_day_plan_url(day, employee_id=employee.pk))


@login_required
@require_http_methods(["GET", "POST"])
def activity_item_edit(request, item_id: int):
    _require_manager(request.user)
    item = get_object_or_404(
        ActivityItem.objects.select_related(
            "employee", "shift", "location", "activity_type"
        ),
        pk=item_id,
    )
    if not can_plan_activity_for_day(request.user, item.employee, item.day):
        raise PermissionDenied
    shifts = published_work_shifts_for_day(item.employee, item.day)
    if request.method == "POST":
        form = ActivityItemForm(
            request.POST,
            instance=item,
            employee=item.employee,
            day=item.day,
            shifts=shifts,
        )
        if form.is_valid():
            try:
                update_activity_item(
                    user=request.user,
                    item=item,
                    location=form.cleaned_data["location"],
                    activity_type=form.cleaned_data["activity_type"],
                    starts_at=form.cleaned_data["starts_at"],
                    ends_at=form.cleaned_data["ends_at"],
                    note=form.cleaned_data.get("note") or "",
                    sort_order=form.cleaned_data.get("sort_order"),
                    expected_version=form.cleaned_data.get("expected_version"),
                    shift=form.cleaned_data["shift"],
                    vehicle=form.cleaned_data.get("vehicle"),
                )
                messages.success(request, "Činnost byla upravena.")
                item.refresh_from_db()
                return HttpResponseRedirect(
                    _day_plan_url(item.day, employee_id=item.employee_id)
                )
            except ActivityConflictError as exc:
                messages.error(request, "; ".join(exc.messages))
    else:
        form = ActivityItemForm(
            instance=item,
            employee=item.employee,
            day=item.day,
            shifts=shifts,
            initial={
                "starts_at": _local_dt_for_input(item.starts_at),
                "ends_at": _local_dt_for_input(item.ends_at),
                "expected_version": item.version,
            },
        )
    return render(
        request,
        "activities/item_form.html",
        {
            "title": "Upravit činnost",
            "form": form,
            "item": item,
        },
    )


@login_required
@require_http_methods(["POST"])
def activity_item_delete(request, item_id: int):
    _require_manager(request.user)
    item = get_object_or_404(ActivityItem, pk=item_id)
    if not can_plan_activity_for_day(request.user, item.employee, item.day):
        raise PermissionDenied
    emp_id, day = item.employee_id, item.day
    delete_activity_item(user=request.user, item=item)
    messages.success(request, "Činnost byla smazána.")
    next_raw = (request.POST.get("next") or "").strip()
    if next_raw.startswith("?"):
        return HttpResponseRedirect(reverse("activity_day") + next_raw)
    return HttpResponseRedirect(_day_plan_url(day, employee_id=emp_id))


def _resolve_export_targets(request):
    """Vrátí (day, employee|None, workplace|None) nebo chybu HttpResponseRedirect/None."""
    day = _parse_day(request.GET.get("day"))
    if day is None:
        messages.error(request, "Neplatný den.")
        return None
    employee = None
    workplace = None
    emp_raw = request.GET.get("employee")
    wp_raw = request.GET.get("workplace")
    if emp_raw:
        employee = get_object_or_404(Employee, pk=emp_raw)
        if not can_plan_activity_for_day(request.user, employee, day):
            messages.error(
                request,
                "Zaměstnanec nemá v tento den publikovanou směnu práce "
                "nebo aktivní pracovní vztah.",
            )
            return None
    if wp_raw:
        workplace = get_object_or_404(Workplace, pk=wp_raw)
    if employee is None and workplace is None:
        messages.error(request, "Zvolte zaměstnance nebo pracoviště.")
        return None
    return day, employee, workplace


@login_required
@require_http_methods(["GET"])
def activity_export(request):
    """Tisková sestava (PDF přes tisk prohlížeče)."""
    try:
        _require_export(request.user)
    except PermissionDenied:
        messages.error(
            request,
            "Nemáte oprávnění exportovat plán činností.",
        )
        return redirect("activity_day")
    resolved = _resolve_export_targets(request)
    if resolved is None:
        return redirect("activity_day")
    day, employee, workplace = resolved
    pack = build_activity_export_pack(
        user=request.user,
        day=day,
        employee=employee,
        workplace=workplace if employee is None else workplace,
    )
    if employee is not None and workplace is None:
        # pracoviště z první směny pro kontext
        if pack.persons and pack.persons[0].shifts:
            workplace = pack.persons[0].shifts[0].workplace
            pack.workplace = workplace
    qs = f"?day={day.isoformat()}"
    if employee:
        qs += f"&employee={employee.pk}"
    if workplace:
        qs += f"&workplace={workplace.pk}"
    return render(
        request,
        "activities/export_day.html",
        {
            "title": "Export plánu činností",
            "pack": pack,
            "xlsx_url": reverse("activity_export_xlsx") + qs,
        },
    )


@login_required
@require_http_methods(["GET"])
def activity_export_xlsx(request):
    try:
        _require_export(request.user)
    except PermissionDenied:
        messages.error(
            request,
            "Nemáte oprávnění exportovat plán činností.",
        )
        return redirect("activity_day")
    resolved = _resolve_export_targets(request)
    if resolved is None:
        return redirect("activity_day")
    day, employee, workplace = resolved
    pack = build_activity_export_pack(
        user=request.user,
        day=day,
        employee=employee,
        workplace=workplace if employee is None else workplace,
    )
    data = build_activity_workbook(pack)
    stamp = day.isoformat()
    if employee:
        name = f"cinnost_{employee.internal_number}_{stamp}.xlsx"
    else:
        wp = workplace.pk if workplace else "wp"
        name = f"cinnost_pracoviste_{wp}_{stamp}.xlsx"
    response = HttpResponse(
        data,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    return response


def _map_city_context(request):
    city_code = request.GET.get("city") or request.session.get("map_city_code")
    city = resolve_map_city(city_code)
    cities = map_cities_active()
    if city:
        request.session["map_city_code"] = city.code
    # Tečka, ne čárka — JS parseFloat("50,411") = 50 → Beroun.
    lat = f"{float(city.center_lat):.6f}" if city else "50.411350"
    lon = f"{float(city.center_lon):.6f}" if city else "14.903180"
    zoom = int(city.default_zoom) if city else 16
    return {
        "map_cities": cities,
        "map_city": city,
        "map_center_lat": lat,
        "map_center_lon": lon,
        "map_zoom": zoom,
    }


@login_required
@require_http_methods(["GET"])
def location_list(request):
    _require_manager(request.user)
    locations = locations_grouped_for_list()
    return render(
        request,
        "activities/location_list.html",
        {
            "title": "Lokality činností",
            "locations": locations,
            "map_geojson": locations_geojson_collection(),
            **_map_city_context(request),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def location_create(request):
    _require_manager(request.user)
    if request.method == "POST":
        form = ActivityLocationForm(request.POST)
        if form.is_valid():
            loc = form.save(commit=False)
            try:
                save_activity_location(user=request.user, location=loc, create=True)
                messages.success(request, "Lokalita byla vytvořena.")
                return redirect("activity_location_list")
            except Exception as exc:
                form.add_error(None, str(exc))
    else:
        form = ActivityLocationForm(
            initial={
                "is_active": True,
                "sort_order": 100,
                "color": next_location_color(),
            }
        )
    return render(
        request,
        "activities/location_form.html",
        {
            "title": "Nová lokalita",
            "form": form,
            "location": None,
            "map_geojson": locations_geojson_collection(),
            **_map_city_context(request),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def location_edit(request, location_id: int):
    _require_manager(request.user)
    location = get_object_or_404(ActivityLocation, pk=location_id)
    if request.method == "POST":
        form = ActivityLocationForm(request.POST, instance=location)
        if form.is_valid():
            loc = form.save(commit=False)
            try:
                save_activity_location(
                    user=request.user, location=loc, create=False
                )
                messages.success(request, "Lokalita byla uložena.")
                return redirect("activity_location_list")
            except Exception as exc:
                form.add_error(None, str(exc))
    else:
        form = ActivityLocationForm(instance=location)
    return render(
        request,
        "activities/location_form.html",
        {
            "title": f"Lokalita {location.code}",
            "form": form,
            "location": location,
            "map_geojson": locations_geojson_collection(exclude_id=location.pk),
            **_map_city_context(request),
        },
    )
