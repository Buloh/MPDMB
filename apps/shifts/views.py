from datetime import date
from calendar import monthrange

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.core.permissions import staff_required
from apps.employees.models import (
    BalancingPeriod,
    Employee,
    WorkTimePreset,
    WorkTimeProfile,
)
from apps.workplaces.models import Workplace

from .forms import (
    BalancingPeriodBulkForm,
    BalancingPeriodForm,
    EmployeeScheduleAssignmentForm,
    GenerateShiftsForm,
    ScheduleTemplateForm,
    ShiftCellForm,
    ShiftCellModalForm,
    ShiftForm,
    ShiftTypeForm,
    WorkTimePresetForm,
)
from .models import (
    WEEKDAY_LABELS_SHORT,
    EmployeeScheduleAssignment,
    ScheduleTemplate,
    Shift,
    ShiftType,
)
from .services import (
    ShiftConflictError,
    assign_shift_cell,
    build_month_matrix,
    can_manage_shift_plan,
    cancel_shift,
    employees_visible_for_shift_plan,
    filter_employees_with_employment_in_range,
    format_hours,
    generate_shifts_from_templates,
    monday_of_week,
    publish_shift,
    resolve_assignment_for_day,
    resolve_template_type,
    types_available_for_employee_day,
    update_shift,
    workplace_for_employee_day,
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
        f"{reverse('shift_month')}?year={year}&month={month}"
    )


@login_required
@require_http_methods(["GET"])
def shift_month(request):
    year, month = _parse_month(request.GET.get("year"), request.GET.get("month"))
    matrix = build_month_matrix(user=request.user, year=year, month=month)
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
        "shifts/month.html",
        {
            "title": "Dlouhodobý plán",
            **matrix,
            "prev_year": prev_year,
            "prev_month": prev_month,
            "next_year": next_year,
            "next_month": next_month,
            "month_label": date(year, month, 1),
        },
    )


shift_week = shift_month


@staff_required
@require_http_methods(["GET", "POST"])
def shift_cell_assign(request):
    year, month = _parse_month(
        request.GET.get("year") or request.POST.get("year"),
        request.GET.get("month") or request.POST.get("month"),
    )
    initial = {
        "employee": request.GET.get("employee"),
        "workplace": request.GET.get("workplace"),
        "day": request.GET.get("day"),
        "shift_type": request.GET.get("shift_type"),
        "publish": True,
    }
    emp_id = request.GET.get("employee")
    day_raw = request.GET.get("day")
    if emp_id and day_raw and request.method == "GET":
        try:
            emp = Employee.objects.get(pk=emp_id)
            day = date.fromisoformat(day_raw)
        except (Employee.DoesNotExist, ValueError, TypeError):
            emp = None
            day = None
        if emp and day:
            asg = resolve_assignment_for_day(emp, day)
            if asg:
                if not initial.get("workplace"):
                    initial["workplace"] = asg.workplace_id
                if not initial.get("shift_type"):
                    st = resolve_template_type(emp, day)
                    if st:
                        initial["shift_type"] = st.pk
    form = ShiftCellForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            assign_shift_cell(
                user=request.user,
                employee=form.cleaned_data["employee"],
                workplace=form.cleaned_data["workplace"],
                day=form.cleaned_data["day"],
                shift_type=form.cleaned_data["shift_type"],
                publish=form.cleaned_data["publish"],
            )
        except (ShiftConflictError, ValidationError) as exc:
            form.add_error(
                None,
                exc.messages[0] if getattr(exc, "messages", None) else str(exc),
            )
        else:
            messages.success(request, "Směna v plánu byla uložena.")
            return _month_redirect(year, month)
    return render(
        request,
        "shifts/cell_form.html",
        {
            "title": "Zapsat směnu do plánu",
            "form": form,
            "year": year,
            "month": month,
        },
    )


@staff_required
@require_http_methods(["GET", "POST"])
def shift_generate_month(request):
    year, month = _parse_month(
        request.GET.get("year") or request.POST.get("year"),
        request.GET.get("month") or request.POST.get("month"),
    )
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
    # POST může mít vlastní interval — před validací bereme měsíc z URL/POST year+month
    date_from = first_day
    date_to = last_day
    if request.method == "POST":
        mode = request.POST.get("range_mode") or GenerateShiftsForm.RANGE_MONTH
        if mode == GenerateShiftsForm.RANGE_CUSTOM:
            try:
                raw_from = request.POST.get("date_from") or ""
                raw_to = request.POST.get("date_to") or ""
                if raw_from and raw_to:
                    date_from = date.fromisoformat(raw_from)
                    date_to = date.fromisoformat(raw_to)
            except ValueError:
                pass
        elif mode == GenerateShiftsForm.RANGE_YEAR:
            try:
                y = int(request.POST.get("year") or year)
                date_from = date(y, 1, 1)
                date_to = date(y, 12, 31)
            except (TypeError, ValueError):
                pass
    emp_qs = filter_employees_with_employment_in_range(
        employees_visible_for_shift_plan(request.user),
        date_from,
        date_to,
    )
    initial = {
        "range_mode": GenerateShiftsForm.RANGE_MONTH,
        "year": year,
        "month": month,
        "date_from": first_day,
        "date_to": last_day,
        "cycle_anchor_date": monday_of_week(first_day),
        "employees": list(emp_qs.values_list("pk", flat=True)),
    }
    default_template = ScheduleTemplate.objects.filter(is_active=True).order_by("name").first()
    if default_template:
        initial["template"] = default_template.pk
    default_wp = Workplace.objects.filter(is_active=True).order_by("name").first()
    if default_wp:
        initial["workplace"] = default_wp.pk
    form = GenerateShiftsForm(
        request.POST or None,
        initial=initial,
        employee_queryset=emp_qs,
    )
    if request.method == "POST" and form.is_valid():
        result = generate_shifts_from_templates(
            user=request.user,
            date_from=form.cleaned_data["date_from"],
            date_to=form.cleaned_data["date_to"],
            template=form.cleaned_data["template"],
            workplace=form.cleaned_data["workplace"],
            cycle_anchor_date=form.cleaned_data["cycle_anchor_date"],
            employee_ids=[e.pk for e in form.cleaned_data["employees"]],
        )
        messages.success(
            request,
            (
                f"Vygenerováno {result['created']} směn. "
                f"Přeskočeno existujících: {result['skipped_existing']}, "
                f"svátků: {result['skipped_holiday']}, "
                f"volných dnů šablony: {result['skipped_empty']}, "
                f"bez pracovního vztahu: {result['skipped_no_employment']}."
            ),
        )
        return _month_redirect(year, month)
    return render(
        request,
        "shifts/generate_form.html",
        {
            "title": "Generovat směny ze šablon",
            "form": form,
            "year": year,
            "month": month,
        },
    )


@staff_required
@require_http_methods(["GET", "POST"])
def shift_cell_modal(request):
    year, month = _parse_month(
        request.GET.get("year") or request.POST.get("year"),
        request.GET.get("month") or request.POST.get("month"),
    )
    partial = (
        request.GET.get("partial") == "1"
        or request.POST.get("partial") == "1"
        or request.headers.get("HX-Request") == "true"
    )
    emp_id = request.GET.get("employee") or request.POST.get("employee")
    day_raw = request.GET.get("day") or request.POST.get("day")
    employee = get_object_or_404(Employee, pk=emp_id)
    try:
        day = date.fromisoformat(day_raw)
    except (TypeError, ValueError):
        if partial:
            return JsonResponse({"ok": False, "error": "Neplatný den."}, status=400)
        messages.error(request, "Neplatný den.")
        return _month_redirect(year, month)

    types = types_available_for_employee_day(employee, day)
    workplace = workplace_for_employee_day(employee, day)
    form = ShiftCellModalForm(
        request.POST or None,
        type_queryset=ShiftType.objects.filter(
            pk__in=[t.pk for t in types]
        ).order_by("sort_order", "code")
        if types
        else ShiftType.objects.none(),
    )
    form_error = None
    if request.method == "POST" and form.is_valid():
        if not workplace:
            form_error = (
                "Zaměstnanec nemá pracoviště pro tento den "
                "(přiřazení šablony ani EmployeeWorkplace)."
            )
            if not partial:
                messages.error(request, form_error)
        else:
            try:
                assign_shift_cell(
                    user=request.user,
                    employee=employee,
                    workplace=workplace,
                    day=day,
                    shift_type=form.cleaned_data["shift_type"],
                    publish=form.cleaned_data["publish"],
                )
            except (ShiftConflictError, ValidationError) as exc:
                form_error = (
                    exc.messages[0] if getattr(exc, "messages", None) else str(exc)
                )
                if not partial:
                    messages.error(request, form_error)
            else:
                if partial:
                    return JsonResponse({"ok": True})
                messages.success(request, "Směna byla přidána.")
                return _month_redirect(year, month)

    wants_json = "application/json" in (request.headers.get("Accept") or "")
    if partial and request.method == "POST" and wants_json:
        if form_error:
            return JsonResponse({"ok": False, "error": form_error}, status=400)
        if not form.is_valid():
            msg = form.errors.as_text() or "Neplatný formulář."
            return JsonResponse({"ok": False, "error": msg}, status=400)

    context = {
        "title": "Přidat směnu",
        "form": form,
        "employee": employee,
        "day": day,
        "year": year,
        "month": month,
        "types": types,
        "workplace": workplace,
        "form_error": form_error,
        "partial": partial,
    }
    if partial:
        return render(request, "shifts/_cell_modal_body.html", context)
    return render(request, "shifts/cell_modal.html", context)


@staff_required
@require_http_methods(["GET"])
def schedule_template_list(request):
    templates = ScheduleTemplate.objects.order_by("name")
    return render(
        request,
        "shifts/template_list.html",
        {"title": "Šablony směn", "templates": templates},
    )


@staff_required
@require_http_methods(["GET", "POST"])
def schedule_template_create(request):
    form = ScheduleTemplateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        template_obj = form.save()
        form.save_slots(template_obj, request.POST)
        messages.success(request, "Šablona směn byla vytvořena.")
        return redirect("schedule_template_list")
    cycle = int(form.data.get("cycle_length") or form.initial.get("cycle_length") or 7)
    return render(
        request,
        "shifts/template_form.html",
        {
            "title": "Nová šablona směn",
            "form": form,
            "template_obj": None,
            "slot_days": _slot_days_context(None, cycle),
            "shift_types": ShiftType.objects.filter(is_active=True).order_by(
                "sort_order", "code"
            ),
        },
    )


@staff_required
@require_http_methods(["GET", "POST"])
def schedule_template_edit(request, pk):
    template_obj = get_object_or_404(ScheduleTemplate, pk=pk)
    form = ScheduleTemplateForm(request.POST or None, instance=template_obj)
    if request.method == "POST" and form.is_valid():
        template_obj = form.save()
        form.save_slots(template_obj, request.POST)
        messages.success(request, "Šablona směn byla uložena.")
        return redirect("schedule_template_list")
    cycle = template_obj.cycle_length
    if request.method == "POST" and form.data.get("cycle_length"):
        try:
            cycle = int(form.data.get("cycle_length"))
        except (TypeError, ValueError):
            cycle = template_obj.cycle_length
    return render(
        request,
        "shifts/template_form.html",
        {
            "title": "Upravit šablonu směn",
            "form": form,
            "template_obj": template_obj,
            "slot_days": _slot_days_context(template_obj, cycle),
            "shift_types": ShiftType.objects.filter(is_active=True).order_by(
                "sort_order", "code"
            ),
        },
    )


def _slot_days_context(template_obj, cycle_length: int):
    selected = {}
    if template_obj and template_obj.pk:
        selected = {
            s.day_index: s.shift_type_id
            for s in template_obj.slots.all()
        }
    rows = []
    for i in range(cycle_length):
        week = i // 7 + 1
        dow = WEEKDAY_LABELS_SHORT[i % 7]
        rows.append(
            {
                "index": i,
                "label": f"Týden {week} · {dow}",
                "selected": selected.get(i),
            }
        )
    return rows


@staff_required
@require_http_methods(["GET"])
def work_time_profile_list(request):
    profiles = list(
        WorkTimeProfile.objects.select_related("employment__employee")
        .order_by("-valid_from")
    )
    for profile in profiles:
        profile.agreed_label = f"{format_hours(profile.agreed_weekly_minutes)} h"
    periods = list(
        BalancingPeriod.objects.select_related(
            "profile__employment__employee"
        ).order_by("-starts_on")
    )
    for period in periods:
        period.target_label = f"{format_hours(period.target_minutes)} h"
    return render(
        request,
        "shifts/fund_list.html",
        {
            "title": "Fond a vyrovnávací období",
            "profiles": profiles,
            "periods": periods,
        },
    )


@staff_required
@require_http_methods(["GET", "POST"])
def work_time_profile_create(request):
    messages.info(
        request,
        "Úvazek nastavíte u zaměstnance (Pracovní vztah), ne zde na Fondu.",
    )
    return redirect("employee_list")


@staff_required
@require_http_methods(["GET", "POST"])
def work_time_profile_bulk_create(request):
    messages.info(
        request,
        "Úvazek nastavíte u jednotlivých zaměstnanců. "
        "Hromadné období zůstává na této stránce Fondu.",
    )
    return redirect("work_time_profile_list")


@staff_required
@require_http_methods(["GET"])
def work_time_preset_list(request):
    presets = WorkTimePreset.objects.order_by("sort_order", "name")
    return render(
        request,
        "shifts/fund_preset_list.html",
        {"title": "Předvolby úvazku", "presets": presets},
    )


@staff_required
@require_http_methods(["GET", "POST"])
def work_time_preset_create(request):
    form = WorkTimePresetForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Předvolba úvazku byla vytvořena.")
        return redirect("work_time_preset_list")
    return render(
        request,
        "shifts/fund_preset_form.html",
        {"title": "Nová předvolba úvazku", "form": form, "preset": None},
    )


@staff_required
@require_http_methods(["GET", "POST"])
def work_time_preset_edit(request, pk):
    preset = get_object_or_404(WorkTimePreset, pk=pk)
    form = WorkTimePresetForm(request.POST or None, instance=preset)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Předvolba úvazku byla uložena.")
        return redirect("work_time_preset_list")
    return render(
        request,
        "shifts/fund_preset_form.html",
        {"title": "Upravit předvolbu úvazku", "form": form, "preset": preset},
    )


@staff_required
@require_http_methods(["GET", "POST"])
def balancing_period_create(request):
    form = BalancingPeriodForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Vyrovnávací období bylo uloženo.")
        return redirect("work_time_profile_list")
    return render(
        request,
        "shifts/fund_period_form.html",
        {"title": "Nové vyrovnávací období", "form": form},
    )


@staff_required
@require_http_methods(["GET", "POST"])
def balancing_period_bulk_create(request):
    from apps.employees.services import bulk_create_balancing_periods

    form = BalancingPeriodBulkForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        result = bulk_create_balancing_periods(
            user=request.user,
            employees=form.cleaned_data.get("employees") or [],
            starts_on=form.cleaned_data["starts_on"],
            ends_on=form.cleaned_data["ends_on"],
            kind=form.cleaned_data["kind"],
            auto_target=form.cleaned_data.get("auto_target", True),
            target_minutes=form.cleaned_data.get("target_minutes"),
            note=form.cleaned_data.get("note") or "",
            all_with_active_profile=form.cleaned_data.get(
                "all_with_active_profile", False
            ),
        )
        if result.created:
            messages.success(
                request,
                f"Vytvořeno {len(result.created)} vyrovnávacích období.",
            )
        for employee, reason in result.skipped:
            messages.warning(
                request,
                f"{employee.last_name} {employee.first_name}: {reason}.",
            )
        if not result.created and not result.skipped:
            messages.info(request, "Nebylo vytvořeno žádné období.")
        return redirect("work_time_profile_list")
    return render(
        request,
        "shifts/fund_bulk_period_form.html",
        {"title": "Stejné období pro více zaměstnanců", "form": form},
    )


@staff_required
@require_http_methods(["GET"])
def schedule_assignment_list(request):
    assignments = (
        EmployeeScheduleAssignment.objects.select_related(
            "employee", "template", "workplace"
        ).order_by("-valid_from", "employee__last_name")
    )
    return render(
        request,
        "shifts/assignment_list.html",
        {"title": "Přiřazení šablon", "assignments": assignments},
    )


@staff_required
@require_http_methods(["GET", "POST"])
def schedule_assignment_create(request):
    form = EmployeeScheduleAssignmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Šablona byla přiřazena zaměstnanci.")
        return redirect("schedule_assignment_list")
    return render(
        request,
        "shifts/assignment_form.html",
        {"title": "Přiřadit šablonu", "form": form, "assignment": None},
    )


@staff_required
@require_http_methods(["GET", "POST"])
def schedule_assignment_edit(request, pk):
    assignment = get_object_or_404(EmployeeScheduleAssignment, pk=pk)
    form = EmployeeScheduleAssignmentForm(
        request.POST or None, instance=assignment
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Přiřazení šablony bylo uloženo.")
        return redirect("schedule_assignment_list")
    return render(
        request,
        "shifts/assignment_form.html",
        {
            "title": "Upravit přiřazení šablony",
            "form": form,
            "assignment": assignment,
        },
    )


@login_required
@require_http_methods(["GET"])
def shift_detail(request, pk):
    shift = get_object_or_404(
        Shift.objects.select_related("employee", "workplace", "shift_type"),
        pk=pk,
    )
    visible_ids = set(
        employees_visible_for_shift_plan(request.user).values_list("pk", flat=True)
    )
    if shift.employee_id not in visible_ids:
        raise PermissionDenied("Nemáte oprávnění zobrazit tuto směnu.")
    if (
        not can_manage_shift_plan(request.user)
        and shift.status != Shift.Status.PUBLISHED
    ):
        raise PermissionDenied("Tato směna ještě není publikovaná.")
    return render(
        request,
        "shifts/detail.html",
        {
            "title": "Detail směny",
            "shift": shift,
            "can_edit": can_manage_shift_plan(request.user),
        },
    )


@staff_required
@require_http_methods(["GET"])
def shift_type_list(request):
    types = ShiftType.objects.order_by("sort_order", "code")
    return render(
        request,
        "shifts/type_list.html",
        {"title": "Typy směn", "shift_types": types},
    )


@staff_required
@require_http_methods(["GET", "POST"])
def shift_type_create(request):
    form = ShiftTypeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Typ směny byl vytvořen.")
        return redirect("shift_type_list")
    return render(
        request,
        "shifts/type_form.html",
        {"title": "Nová směna (typ)", "form": form, "shift_type": None},
    )


@staff_required
@require_http_methods(["GET", "POST"])
def shift_type_edit(request, pk):
    shift_type = get_object_or_404(ShiftType, pk=pk)
    form = ShiftTypeForm(request.POST or None, instance=shift_type)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Typ směny byl uložen.")
        return redirect("shift_type_list")
    return render(
        request,
        "shifts/type_form.html",
        {"title": "Upravit typ směny", "form": form, "shift_type": shift_type},
    )


@staff_required
@require_http_methods(["GET"])
def shift_create(request):
    """Dříve vázáno na zaměstnance – přesměrování na definici typu."""
    return redirect("shift_type_create")


@staff_required
@require_http_methods(["GET", "POST"])
def shift_edit(request, pk):
    shift = get_object_or_404(Shift, pk=pk)
    if shift.status == Shift.Status.CANCELLED:
        messages.error(request, "Zrušenou směnu nelze upravit.")
        return redirect("shift_detail", pk=shift.pk)
    form = ShiftForm(request.POST or None, instance=shift)
    if request.method == "POST" and form.is_valid():
        updated = form.save(commit=False)
        expected = int(request.POST.get("version") or shift.version)
        try:
            shift = update_shift(
                user=request.user,
                shift=updated,
                expected_version=expected,
            )
        except ShiftConflictError as exc:
            form.add_error(None, exc.messages[0] if exc.messages else str(exc))
        except ValidationError as exc:
            form.add_error(None, exc.messages[0] if exc.messages else str(exc))
        else:
            messages.success(request, "Směna byla uložena.")
            return redirect("shift_detail", pk=shift.pk)
    return render(
        request,
        "shifts/form.html",
        {"title": "Upravit směnu", "form": form, "shift": shift},
    )


@staff_required
@require_http_methods(["POST"])
def shift_publish(request, pk):
    shift = get_object_or_404(Shift, pk=pk)
    expected = int(request.POST.get("version") or shift.version)
    try:
        publish_shift(user=request.user, shift=shift, expected_version=expected)
        messages.success(request, "Směna byla publikována.")
    except (ShiftConflictError, ValidationError) as exc:
        messages.error(
            request, exc.messages[0] if getattr(exc, "messages", None) else str(exc)
        )
    return redirect("shift_detail", pk=pk)


@staff_required
@require_http_methods(["POST"])
def shift_cancel(request, pk):
    shift = get_object_or_404(Shift, pk=pk)
    expected = int(request.POST.get("version") or shift.version)
    try:
        cancel_shift(user=request.user, shift=shift, expected_version=expected)
        messages.success(request, "Směna byla zrušena.")
    except (ShiftConflictError, ValidationError) as exc:
        messages.error(
            request, exc.messages[0] if getattr(exc, "messages", None) else str(exc)
        )
    return redirect("shift_detail", pk=pk)
