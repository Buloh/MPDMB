"""Views roční dovolené."""

from __future__ import annotations

from datetime import date as date_cls

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.employees.models import Employee
from apps.workplaces.models import Workplace

from .calendar_view import WEEKDAY_HEADERS, employees_for_workplace_year
from .forms import LeavePlanForm
from .models import LeavePlan
from .services import (
    LeaveConflictError,
    approve_leave_plan,
    cancel_leave_plan,
    can_access_employee_leave,
    can_manage_leave,
    create_leave_plan,
    employee_year_detail,
    half_day_allowed,
    year_overview,
)


def _parse_year(raw) -> int:
    today = timezone.localdate()
    try:
        year = int(raw) if raw else today.year
        if year < 2000 or year > 2100:
            raise ValueError
    except (TypeError, ValueError):
        year = today.year
    return year


def _wants_json(request) -> bool:
    accept = request.headers.get("Accept", "")
    return "application/json" in accept or request.GET.get("format") == "json"


@login_required
@require_http_methods(["GET"])
def leave_year(request):
    year = _parse_year(request.GET.get("year"))
    data = year_overview(user=request.user, year=year)
    workplaces = Workplace.objects.filter(is_active=True).order_by("name")
    return render(
        request,
        "leave/year.html",
        {
            "title": f"Dovolená {year}",
            **data,
            "prev_year": year - 1,
            "next_year": year + 1,
            "workplaces": workplaces,
        },
    )


@login_required
@require_http_methods(["GET"])
def leave_employee(request, employee_id: int):
    employee = get_object_or_404(Employee, pk=employee_id)
    if not can_access_employee_leave(request.user, employee):
        raise PermissionDenied
    year = _parse_year(request.GET.get("year"))
    try:
        detail = employee_year_detail(
            user=request.user, employee=employee, year=year
        )
    except LeaveConflictError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect(f"{reverse('leave_year')}?year={year}")
    except PermissionError:
        raise PermissionDenied from None

    return render(
        request,
        "leave/employee.html",
        {
            "title": f"Dovolená · {employee}",
            **detail,
            "prev_year": year - 1,
            "next_year": year + 1,
            "weekday_headers": WEEKDAY_HEADERS,
        },
    )


@login_required
@require_http_methods(["GET"])
def leave_workplace(request, workplace_id: int):
    if not can_manage_leave(request.user):
        raise PermissionDenied
    workplace = get_object_or_404(Workplace, pk=workplace_id)
    year = _parse_year(request.GET.get("year"))
    rows = employees_for_workplace_year(workplace, year)
    return render(
        request,
        "leave/workplace.html",
        {
            "title": f"Dovolená · {workplace.name}",
            "workplace": workplace,
            "year": year,
            "rows": rows,
            "can_manage": True,
            "prev_year": year - 1,
            "next_year": year + 1,
            "weekday_headers": WEEKDAY_HEADERS,
            "workplaces": Workplace.objects.filter(is_active=True).order_by(
                "name"
            ),
        },
    )


@login_required
@require_http_methods(["GET"])
def leave_plan_form_partial(request):
    """Tělo modalu pro nový blok dovolené."""
    if not can_manage_leave(request.user):
        raise PermissionDenied
    employee = get_object_or_404(
        Employee, pk=request.GET.get("employee_id")
    )
    year = _parse_year(request.GET.get("year"))
    try:
        detail = employee_year_detail(
            user=request.user, employee=employee, year=year
        )
    except (LeaveConflictError, PermissionError):
        raise PermissionDenied from None

    starts = request.GET.get("starts_on") or ""
    ends = request.GET.get("ends_on") or ""
    initial = {"approve_now": True}
    if starts:
        try:
            initial["starts_on"] = date_cls.fromisoformat(starts)
        except ValueError:
            pass
    if ends:
        try:
            initial["ends_on"] = date_cls.fromisoformat(ends)
        except ValueError:
            pass
    form = LeavePlanForm(
        initial=initial,
        allow_half_day=detail.get("allow_half_day", True),
    )
    return render(
        request,
        "leave/_plan_dialog_body.html",
        {
            "form": form,
            "employee": employee,
            "year": year,
            "allow_half_day": detail.get("allow_half_day", True),
            "remaining_label": detail.get("remaining_label", ""),
        },
    )


@login_required
@require_http_methods(["POST"])
def leave_plan_create(request):
    """Vytvoření plánu z modalu (JSON při Accept: application/json)."""
    if not can_manage_leave(request.user):
        raise PermissionDenied
    employee = get_object_or_404(
        Employee, pk=request.POST.get("employee_id")
    )
    year = _parse_year(request.POST.get("year"))
    try:
        detail = employee_year_detail(
            user=request.user, employee=employee, year=year
        )
    except (LeaveConflictError, PermissionError) as exc:
        if _wants_json(request):
            msg = (
                "; ".join(exc.messages)
                if isinstance(exc, LeaveConflictError)
                else "Nemáte oprávnění."
            )
            return JsonResponse({"ok": False, "error": msg}, status=400)
        raise PermissionDenied from None

    form = LeavePlanForm(
        request.POST,
        allow_half_day=half_day_allowed(detail["employment"]),
    )
    if not form.is_valid():
        if _wants_json(request):
            errors = {
                k: [str(e) for e in v] for k, v in form.errors.items()
            }
            return JsonResponse(
                {"ok": False, "error": "Opravte chyby ve formuláři.", "errors": errors},
                status=400,
            )
        messages.error(request, "Opravte chyby ve formuláři.")
        return redirect(
            f"{reverse('leave_employee', args=[employee.pk])}?year={year}"
        )

    try:
        plan = create_leave_plan(
            user=request.user,
            employment=detail["employment"],
            year=year,
            starts_on=form.cleaned_data["starts_on"],
            ends_on=form.cleaned_data["ends_on"],
            note=form.cleaned_data.get("note") or "",
            approve=bool(form.cleaned_data.get("approve_now")),
            portion=form.cleaned_data.get("portion") or "full",
        )
    except LeaveConflictError as exc:
        msg = "; ".join(exc.messages)
        if _wants_json(request):
            return JsonResponse({"ok": False, "error": msg}, status=400)
        messages.error(request, msg)
        return redirect(
            f"{reverse('leave_employee', args=[employee.pk])}?year={year}"
        )

    if plan.status == LeavePlan.Status.APPROVED:
        msg = "Dovolená schválena a propsána do dlouhodobého plánu."
    else:
        msg = "Návrh dovolené byl uložen."
    warning = getattr(plan, "_leave_warning", None)
    if _wants_json(request):
        payload = {
            "ok": True,
            "message": msg,
            "plan_id": plan.pk,
            "reload": True,
        }
        if warning:
            payload["warning"] = warning
        return JsonResponse(payload)
    messages.success(request, msg)
    if warning:
        messages.warning(request, warning)
    return redirect(
        f"{reverse('leave_employee', args=[employee.pk])}?year={year}"
    )


@login_required
@require_http_methods(["POST"])
def leave_plan_approve(request, plan_id: int):
    if not can_manage_leave(request.user):
        raise PermissionDenied
    plan = get_object_or_404(LeavePlan, pk=plan_id)
    year = plan.year
    emp_id = plan.employment.employee_id
    next_url = request.POST.get("next") or (
        f"{reverse('leave_employee', args=[emp_id])}?year={year}"
    )
    try:
        plan = approve_leave_plan(user=request.user, plan=plan)
        messages.success(request, "Plán dovolené schválen a propsán do směn.")
        warning = getattr(plan, "_leave_warning", None)
        if warning:
            messages.warning(request, warning)
    except LeaveConflictError as exc:
        messages.error(request, "; ".join(exc.messages))
    return HttpResponseRedirect(next_url)


@login_required
@require_http_methods(["POST"])
def leave_plan_cancel(request, plan_id: int):
    if not can_manage_leave(request.user):
        raise PermissionDenied
    plan = get_object_or_404(LeavePlan, pk=plan_id)
    year = plan.year
    emp_id = plan.employment.employee_id
    next_url = request.POST.get("next") or (
        f"{reverse('leave_employee', args=[emp_id])}?year={year}"
    )
    try:
        cancel_leave_plan(user=request.user, plan=plan)
        messages.success(request, "Plán dovolené zrušen (směny odstraněny).")
    except LeaveConflictError as exc:
        messages.error(request, "; ".join(exc.messages))
    return HttpResponseRedirect(next_url)
