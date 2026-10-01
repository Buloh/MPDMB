"""Views docházky."""

from __future__ import annotations

from datetime import date, datetime, time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.employees.models import Employee
from apps.shifts.fund import format_hours
from apps.shifts.models import Shift, ShiftType
from apps.workplaces.models import Workplace

from .export_xlsx import build_attendance_workbook
from .forms import (
    AbsenceForm,
    AdHocWorkForm,
    ConfirmWorkForm,
    local_time_for_input,
)
from .models import AbsenceType, WorkInterval
from .services import (
    AttendanceConflictError,
    MISSING_EMPLOYMENT_CODE,
    attendance_day_detail,
    can_access_employee_attendance,
    can_manage_attendance,
    clear_attendance_for_shift,
    confirm_work_interval,
    create_ad_hoc_work_interval,
    delete_ad_hoc_work_interval,
    month_attendance_matrix,
    propose_from_published_shifts,
    set_absence_for_shift,
    shift_local_day,
    workplaces_for_employee_day,
)


def _parse_month(year_raw, month_raw):
    today = timezone.localdate()
    try:
        year = int(year_raw) if year_raw else today.year
        month = int(month_raw) if month_raw else today.month
        if month < 1 or month > 12:
            raise ValueError
        date(year, month, 1)
    except (TypeError, ValueError):
        year, month = today.year, today.month
    return year, month


def _month_redirect(year, month):
    return HttpResponseRedirect(
        f"{reverse('attendance_month')}?year={year}&month={month}"
    )


def _wants_partial(request) -> bool:
    if request.POST.get("partial") == "1":
        return True
    accept = request.headers.get("Accept") or ""
    return "application/json" in accept


def _partial_or_redirect(
    request,
    shift,
    year,
    month,
    *,
    ok: bool,
    error: str = "",
    employee_url: str = "",
):
    if _wants_partial(request):
        if ok:
            return JsonResponse({"ok": True})
        payload = {"ok": False, "error": error or "Akce selhala."}
        if employee_url:
            payload["employee_url"] = employee_url
        return JsonResponse(payload)
    return _redirect_after_action(request, shift, year, month)


def _conflict_error_text(exc: AttendanceConflictError) -> str:
    msgs = getattr(exc, "messages", None)
    if msgs:
        return "; ".join(str(m) for m in msgs)
    return str(exc)


def _is_missing_employment(exc: AttendanceConflictError) -> bool:
    if getattr(exc, "code", None) == MISSING_EMPLOYMENT_CODE:
        return True
    text = _conflict_error_text(exc)
    return "pracovní vztah" in text


def _employee_edit_url(employee: Employee) -> str:
    return reverse("employee_edit", args=[employee.pk])


def _conflict_json(exc: AttendanceConflictError, employee: Employee | None = None):
    payload = {"ok": False, "error": _conflict_error_text(exc)}
    url = _employee_url_for_conflict(exc, employee)
    if url:
        payload["employee_url"] = url
    return JsonResponse(payload)


def _employee_url_for_conflict(
    exc: AttendanceConflictError, employee: Employee | None
) -> str:
    if employee is not None and _is_missing_employment(exc):
        return _employee_edit_url(employee)
    return ""


def _adhoc_work_shift_types():
    return list(
        ShiftType.objects.filter(
            is_active=True,
            counts_as_work=True,
            kind=ShiftType.Kind.WORK,
        ).order_by("sort_order", "code")
    )


@login_required
@require_http_methods(["GET"])
def attendance_month(request):
    year, month = _parse_month(request.GET.get("year"), request.GET.get("month"))
    show_long_plan = request.GET.get("plan") == "1"
    matrix = month_attendance_matrix(user=request.user, year=year, month=month)
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1
    return render(
        request,
        "attendance/month.html",
        {
            "title": "Docházka",
            **matrix,
            "prev_year": prev_year,
            "prev_month": prev_month,
            "next_year": next_year,
            "next_month": next_month,
            "month_label": date(year, month, 1),
            "format_hours": format_hours,
            "adhoc_shift_types": _adhoc_work_shift_types(),
            "adhoc_workplaces": list(
                Workplace.objects.filter(is_active=True).order_by("name")
            ),
            "adhoc_post_url": reverse("attendance_adhoc_form"),
            "show_long_plan": show_long_plan,
        },
    )


@login_required
@require_http_methods(["GET"])
def attendance_export_xlsx(request):
    if not can_manage_attendance(request.user):
        raise PermissionDenied
    year, month = _parse_month(request.GET.get("year"), request.GET.get("month"))
    payload = build_attendance_workbook(
        user=request.user, year=year, month=month
    )
    filename = f"dochazka_{year}-{month:02d}.xlsx"
    response = HttpResponse(
        payload,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_http_methods(["GET", "POST"])
def attendance_day(request):
    year, month = _parse_month(
        request.GET.get("year") or request.POST.get("year"),
        request.GET.get("month") or request.POST.get("month"),
    )
    emp_id = request.GET.get("employee") or request.POST.get("employee")
    day_raw = request.GET.get("day") or request.POST.get("day")
    employee = get_object_or_404(Employee, pk=emp_id)
    if not can_access_employee_attendance(request.user, employee):
        raise PermissionDenied
    try:
        day = date.fromisoformat(str(day_raw))
    except (TypeError, ValueError):
        if request.GET.get("partial") == "1":
            return JsonResponse({"ok": False, "error": "Neplatný den."})
        messages.error(request, "Neplatný den.")
        return _month_redirect(year, month)

    detail = attendance_day_detail(
        user=request.user, employee=employee, day=day
    )
    context = {
        "title": f"Docházka · {day:%d.%m.%Y}",
        "year": year,
        "month": month,
        **detail,
        "format_hours": format_hours,
    }
    if request.GET.get("partial") == "1":
        return render(request, "attendance/_day_modal_body.html", context)
    return render(request, "attendance/day.html", context)


@login_required
@require_http_methods(["POST"])
def attendance_confirm(request, shift_id: int):
    shift = get_object_or_404(
        Shift.objects.select_related("employee", "shift_type", "workplace"),
        pk=shift_id,
    )
    if not can_access_employee_attendance(request.user, shift.employee):
        raise PermissionDenied
    year, month = _parse_month(request.POST.get("year"), request.POST.get("month"))
    as_plan = request.POST.get("as_plan") == "1"
    if as_plan:
        try:
            confirm_work_interval(user=request.user, shift=shift)
            messages.success(request, "Práce potvrzena podle plánu.")
            return _partial_or_redirect(request, shift, year, month, ok=True)
        except AttendanceConflictError as exc:
            err = _conflict_error_text(exc)
            messages.error(request, err)
            return _partial_or_redirect(
                request,
                shift,
                year,
                month,
                ok=False,
                error=err,
                employee_url=_employee_url_for_conflict(exc, shift.employee),
            )

    form = ConfirmWorkForm(request.POST)
    if form.is_valid():
        try:
            day = shift_local_day(shift)
            starts_at, ends_at = form.datetimes_for_day(day)
            confirm_work_interval(
                user=request.user,
                shift=shift,
                starts_at=starts_at,
                ends_at=ends_at,
                break_minutes=form.cleaned_data["break_minutes"],
                expected_version=form.cleaned_data.get("expected_version"),
                note=form.cleaned_data.get("note") or "",
            )
            messages.success(request, "Práce potvrzena.")
            return _partial_or_redirect(request, shift, year, month, ok=True)
        except AttendanceConflictError as exc:
            err = _conflict_error_text(exc)
            messages.error(request, err)
            return _partial_or_redirect(
                request,
                shift,
                year,
                month,
                ok=False,
                error=err,
                employee_url=_employee_url_for_conflict(exc, shift.employee),
            )
    err = "Neplatné údaje pro potvrzení práce."
    messages.error(request, err)
    return _partial_or_redirect(request, shift, year, month, ok=False, error=err)


@login_required
@require_http_methods(["GET", "POST"])
def attendance_confirm_form(request, shift_id: int):
    shift = get_object_or_404(
        Shift.objects.select_related("employee", "shift_type", "workplace"),
        pk=shift_id,
    )
    if not can_access_employee_attendance(request.user, shift.employee):
        raise PermissionDenied
    year, month = _parse_month(
        request.GET.get("year") or request.POST.get("year"),
        request.GET.get("month") or request.POST.get("month"),
    )
    partial = (
        request.GET.get("partial") == "1"
        or request.POST.get("partial") == "1"
        or _wants_partial(request)
    )
    existing = WorkInterval.objects.filter(shift=shift).order_by("-id").first()
    src_start = existing.starts_at if existing else shift.starts_at
    src_end = existing.ends_at if existing else shift.ends_at
    initial = {
        "start_time": local_time_for_input(src_start),
        "end_time": local_time_for_input(src_end),
        "break_minutes": (
            existing.break_minutes
            if existing
            else (shift.shift_type.break_minutes if shift.shift_type_id else 0)
        ),
        "expected_version": existing.version if existing else None,
        "note": existing.note if existing else "",
    }
    form = ConfirmWorkForm(request.POST or None, initial=initial)
    day = shift_local_day(shift)
    context = {
        "title": "Upravit a potvrdit práci",
        "form": form,
        "shift": shift,
        "year": year,
        "month": month,
        "day": day,
        "format_hours": format_hours,
        "partial": partial,
    }
    if request.method == "POST":
        if form.is_valid():
            try:
                starts_at, ends_at = form.datetimes_for_day(day)
                confirm_work_interval(
                    user=request.user,
                    shift=shift,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    break_minutes=form.cleaned_data["break_minutes"],
                    expected_version=form.cleaned_data.get("expected_version"),
                    note=form.cleaned_data.get("note") or "",
                )
            except AttendanceConflictError as exc:
                err = _conflict_error_text(exc)
                if partial:
                    return _conflict_json(exc, shift.employee)
                messages.error(request, err)
            else:
                if partial:
                    return JsonResponse({"ok": True})
                messages.success(request, "Práce potvrzena.")
                return _redirect_after_action(request, shift, year, month)
        elif partial:
            bits = []
            for field, errors in form.errors.items():
                bits.extend(f"{field}: {e}" for e in errors)
            return JsonResponse(
                {"ok": False, "error": "; ".join(bits) or "Neplatný formulář."}
            )
    if partial and request.method == "GET":
        return render(request, "attendance/_confirm_modal_body.html", context)
    return render(request, "attendance/confirm_form.html", context)


@login_required
@require_http_methods(["POST"])
def attendance_absence(request, shift_id: int):
    shift = get_object_or_404(
        Shift.objects.select_related("employee", "shift_type"),
        pk=shift_id,
    )
    if not can_access_employee_attendance(request.user, shift.employee):
        raise PermissionDenied
    year, month = _parse_month(request.POST.get("year"), request.POST.get("month"))
    code = (request.POST.get("absence_code") or "").strip()
    if code:
        absence_type = get_object_or_404(AbsenceType, code=code, is_active=True)
        try:
            set_absence_for_shift(
                user=request.user,
                shift=shift,
                absence_type=absence_type,
                note=request.POST.get("note") or "",
            )
            messages.success(request, f"Zapsána absence: {absence_type.name}.")
            return _partial_or_redirect(request, shift, year, month, ok=True)
        except AttendanceConflictError as exc:
            err = _conflict_error_text(exc)
            messages.error(request, err)
            return _partial_or_redirect(
                request,
                shift,
                year,
                month,
                ok=False,
                error=err,
                employee_url=_employee_url_for_conflict(exc, shift.employee),
            )

    form = AbsenceForm(request.POST)
    if form.is_valid():
        try:
            set_absence_for_shift(
                user=request.user,
                shift=shift,
                absence_type=form.cleaned_data["absence_type"],
                note=form.cleaned_data.get("note") or "",
            )
            messages.success(
                request,
                f"Zapsána absence: {form.cleaned_data['absence_type'].name}.",
            )
            return _partial_or_redirect(request, shift, year, month, ok=True)
        except AttendanceConflictError as exc:
            err = _conflict_error_text(exc)
            messages.error(request, err)
            return _partial_or_redirect(
                request,
                shift,
                year,
                month,
                ok=False,
                error=err,
                employee_url=_employee_url_for_conflict(exc, shift.employee),
            )
    err = "Neplatný typ absence."
    messages.error(request, err)
    return _partial_or_redirect(request, shift, year, month, ok=False, error=err)


@login_required
@require_http_methods(["POST"])
def attendance_clear(request, shift_id: int):
    shift = get_object_or_404(
        Shift.objects.select_related("employee"),
        pk=shift_id,
    )
    if not can_access_employee_attendance(request.user, shift.employee):
        raise PermissionDenied
    year, month = _parse_month(request.POST.get("year"), request.POST.get("month"))
    clear_attendance_for_shift(user=request.user, shift=shift)
    messages.success(request, "Docházka u směny zrušena (nevyřešeno).")
    return _partial_or_redirect(request, shift, year, month, ok=True)


@login_required
@require_http_methods(["GET", "POST"])
def attendance_adhoc_form(request):
    if not can_manage_attendance(request.user):
        raise PermissionDenied
    year, month = _parse_month(
        request.GET.get("year") or request.POST.get("year"),
        request.GET.get("month") or request.POST.get("month"),
    )
    emp_id = request.GET.get("employee") or request.POST.get("employee")
    day_raw = request.GET.get("day") or request.POST.get("day")
    employee = get_object_or_404(Employee, pk=emp_id)
    if not can_access_employee_attendance(request.user, employee):
        raise PermissionDenied
    try:
        day = date.fromisoformat(str(day_raw))
    except (TypeError, ValueError):
        if _wants_partial(request):
            return JsonResponse({"ok": False, "error": "Neplatný den."})
        messages.error(request, "Neplatný den.")
        return _month_redirect(year, month)

    workplaces = workplaces_for_employee_day(employee, day)
    wants_json = _wants_partial(request)

    if request.method == "POST" and request.POST.get("shift_type"):
        try:
            shift_type = ShiftType.objects.get(
                pk=request.POST.get("shift_type"),
                is_active=True,
                counts_as_work=True,
                kind=ShiftType.Kind.WORK,
            )
        except (ShiftType.DoesNotExist, ValueError, TypeError):
            if wants_json:
                return JsonResponse(
                    {"ok": False, "error": "Neplatný typ směny."}
                )
            messages.error(request, "Neplatný typ směny.")
            return _month_redirect(year, month)
        workplace = None
        wp_raw = request.POST.get("workplace")
        if wp_raw:
            workplace = workplaces.filter(pk=wp_raw).first()
        if workplace is None:
            workplace = workplaces.first()
        if workplace is None:
            if wants_json:
                return JsonResponse(
                    {"ok": False, "error": "Chybí pracoviště."}
                )
            messages.error(request, "Chybí pracoviště.")
            return _month_redirect(year, month)
        starts_at, ends_at = shift_type.bounds_for_date(day)
        try:
            create_ad_hoc_work_interval(
                user=request.user,
                employee=employee,
                workplace=workplace,
                starts_at=starts_at,
                ends_at=ends_at,
                break_minutes=shift_type.break_minutes,
                note="",
            )
        except AttendanceConflictError as exc:
            if wants_json:
                return _conflict_json(exc, employee)
            messages.error(request, _conflict_error_text(exc))
            return _month_redirect(year, month)
        if wants_json:
            return JsonResponse({"ok": True})
        messages.success(request, "Ad-hoc práce byla zapsána.")
        return HttpResponseRedirect(
            f"{reverse('attendance_day')}?employee={employee.pk}"
            f"&day={day.isoformat()}&year={year}&month={month}"
        )

    initial = {
        "start_time": time(8, 0),
        "end_time": time(16, 0),
        "break_minutes": 30,
        "workplace": workplaces.first() if workplaces.exists() else None,
    }
    form = AdHocWorkForm(
        request.POST or None,
        workplace_queryset=workplaces,
        initial=initial,
    )
    if request.method == "POST":
        if form.is_valid():
            try:
                starts_at, ends_at = form.datetimes_for_day(day)
                create_ad_hoc_work_interval(
                    user=request.user,
                    employee=employee,
                    workplace=form.cleaned_data["workplace"],
                    starts_at=starts_at,
                    ends_at=ends_at,
                    break_minutes=form.cleaned_data["break_minutes"],
                    note=form.cleaned_data.get("note") or "",
                )
            except AttendanceConflictError as exc:
                err = _conflict_error_text(exc)
                if wants_json:
                    return _conflict_json(exc, employee)
                messages.error(request, err)
            else:
                if wants_json:
                    return JsonResponse({"ok": True})
                messages.success(request, "Ad-hoc práce byla zapsána.")
                return HttpResponseRedirect(
                    f"{reverse('attendance_day')}?employee={employee.pk}"
                    f"&day={day.isoformat()}&year={year}&month={month}"
                )
        elif wants_json:
            bits = []
            for field, errors in form.errors.items():
                bits.extend(f"{field}: {e}" for e in errors)
            return JsonResponse(
                {"ok": False, "error": "; ".join(bits) or "Neplatný formulář."}
            )
    return render(
        request,
        "attendance/adhoc_form.html",
        {
            "title": "Přidat práci (mimo plán)",
            "form": form,
            "employee": employee,
            "day": day,
            "year": year,
            "month": month,
        },
    )


@login_required
@require_http_methods(["POST"])
def attendance_adhoc_delete(request, interval_id: int):
    if not can_manage_attendance(request.user):
        raise PermissionDenied
    interval = get_object_or_404(
        WorkInterval.objects.select_related("employment__employee"),
        pk=interval_id,
    )
    employee = interval.employment.employee
    if not can_access_employee_attendance(request.user, employee):
        raise PermissionDenied
    year, month = _parse_month(request.POST.get("year"), request.POST.get("month"))
    day = timezone.localtime(interval.starts_at).date()
    try:
        delete_ad_hoc_work_interval(user=request.user, interval=interval)
        messages.success(request, "Ad-hoc práce byla smazána.")
    except AttendanceConflictError as exc:
        messages.error(request, "; ".join(exc.messages))
    return HttpResponseRedirect(
        f"{reverse('attendance_day')}?employee={employee.pk}"
        f"&day={day.isoformat()}&year={year}&month={month}"
    )


@login_required
@require_http_methods(["POST"])
def attendance_propose(request):
    if not can_manage_attendance(request.user):
        raise PermissionDenied
    year, month = _parse_month(request.POST.get("year"), request.POST.get("month"))
    emp_id = request.POST.get("employee")
    if emp_id:
        employees = [get_object_or_404(Employee, pk=emp_id)]
        if not can_access_employee_attendance(request.user, employees[0]):
            raise PermissionDenied
    else:
        from .services import employees_visible_for_attendance

        employees = list(employees_visible_for_attendance(request.user))
    total = 0
    for emp in employees:
        total += len(propose_from_published_shifts(emp, year, month))
    messages.success(
        request,
        f"Obnoveno {total} návrhů docházky z publikovaných směn.",
    )
    return _month_redirect(year, month)


def _redirect_after_action(request, shift, year, month):
    day = timezone.localtime(shift.starts_at).date()
    next_url = request.POST.get("next") or ""
    if next_url.startswith("/"):
        return redirect(next_url)
    return HttpResponseRedirect(
        f"{reverse('attendance_day')}?employee={shift.employee_id}"
        f"&day={day.isoformat()}&year={year}&month={month}"
    )
