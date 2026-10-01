from django.contrib import messages
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.core.permissions import staff_required
from apps.documents.access import (
    can_manage_stored_documents,
    can_view_employee_documents,
)
from apps.documents.services import list_documents_for_employee
from apps.leave.forms import EmployeeLeaveSettingsForm
from apps.leave.models import EmployeeLeaveSettings

from .forms import (
    EmployeeForm,
    EmployeeQualificationFormSet,
    EmployeeWorkTimeForm,
    EmployeeWorkplaceFormSet,
    EmploymentForm,
)
from .models import Employee, Employment, WorkTimeProfile
from .services import archive_employee, save_employee_bundle


def _employment_for_form(employee: Employee | None) -> Employment | None:
    if employee is None:
        return None
    return employee.current_employment or employee.employments.order_by(
        "-started_on"
    ).first()


def _qualification_formset(request, employee: Employee | None):
    instance = employee if employee is not None else Employee()
    return EmployeeQualificationFormSet(
        request.POST or None,
        instance=instance,
        prefix="qual",
    )


def _workplace_formset(request, employee: Employee | None):
    instance = employee if employee is not None else Employee()
    return EmployeeWorkplaceFormSet(
        request.POST or None,
        instance=instance,
        prefix="wp",
    )


def _work_time_form(request, employment: Employment | None):
    profile = None
    if employment is not None:
        profile = (
            WorkTimeProfile.objects.filter(employment=employment, is_active=True)
            .order_by("-valid_from")
            .first()
        )
    return EmployeeWorkTimeForm(
        request.POST or None,
        prefix="wt",
        profile=profile,
    )


def _leave_settings_form(request, employment: Employment | None):
    instance = None
    if employment is not None:
        instance = EmployeeLeaveSettings.objects.filter(
            employment=employment
        ).first()
    return EmployeeLeaveSettingsForm(
        request.POST or None,
        instance=instance,
        prefix="leave",
    )


def _employee_form_context(
    *,
    title: str,
    form,
    employment_form,
    qualification_formset,
    work_time_form,
    workplace_formset,
    employee,
    leave_settings_form=None,
):
    return {
        "title": title,
        "form": form,
        "employment_form": employment_form,
        "qualification_formset": qualification_formset,
        "work_time_form": work_time_form,
        "workplace_formset": workplace_formset,
        "employee": employee,
        "leave_settings_form": leave_settings_form,
    }


@staff_required
@require_http_methods(["GET"])
def employee_list(request):
    q = request.GET.get("q", "").strip()
    show_archived = request.GET.get("archived") == "1"
    employees = Employee.objects.select_related("user").prefetch_related(
        Prefetch(
            "employments",
            queryset=Employment.objects.order_by("-started_on"),
        ),
        "qualifications__qualification_type",
    )
    if not show_archived:
        employees = employees.filter(is_active=True)
    if q:
        employees = employees.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(internal_number__icontains=q)
            | Q(job_title__icontains=q)
            | Q(phone__icontains=q)
            | Q(email__icontains=q)
        )
    return render(
        request,
        "employees/list.html",
        {
            "title": "Zaměstnanci",
            "employees": employees,
            "q": q,
            "show_archived": show_archived,
        },
    )


@staff_required
@require_http_methods(["GET"])
def employee_detail(request, pk):
    employee = get_object_or_404(
        Employee.objects.select_related("user").prefetch_related(
            "workplace_assignments__workplace",
            "employments",
            "qualifications__qualification_type",
        ),
        pk=pk,
    )
    qualifications = employee.active_qualifications()
    employment = employee.current_employment
    profile = None
    if employment:
        profile = (
            WorkTimeProfile.objects.filter(employment=employment, is_active=True)
            .order_by("-valid_from")
            .first()
        )
        if profile:
            mins = profile.agreed_weekly_minutes
            h, m = mins // 60, mins % 60
            profile.agreed_label = f"{h}:{m:02d}" if m else f"{h}"
    stored_documents = []
    if can_view_employee_documents(request.user, employee):
        stored_documents = list_documents_for_employee(employee)
    return render(
        request,
        "employees/detail.html",
        {
            "title": employee.full_name,
            "employee": employee,
            "employment": employment,
            "work_time_profile": profile,
            "qualifications": qualifications,
            "has_expired_qualifications": employee.has_expired_qualifications,
            "stored_documents": stored_documents,
            "can_manage_stored_docs": can_manage_stored_documents(request.user),
        },
    )


@staff_required
@require_http_methods(["GET", "POST"])
def employee_create(request):
    form = EmployeeForm(request.POST or None)
    employment_form = EmploymentForm(request.POST or None, prefix="emp")
    qualification_formset = _qualification_formset(request, None)
    work_time_form = _work_time_form(request, None)
    workplace_formset = _workplace_formset(request, None)
    leave_settings_form = _leave_settings_form(request, None)
    if (
        request.method == "POST"
        and form.is_valid()
        and employment_form.is_valid()
        and qualification_formset.is_valid()
        and work_time_form.is_valid()
        and workplace_formset.is_valid()
        and leave_settings_form.is_valid()
    ):
        employee = form.save(commit=False)
        employment = employment_form.save(commit=False)
        save_employee_bundle(
            user=request.user,
            employee=employee,
            employment=employment,
            qualification_formset=qualification_formset,
            creating=True,
            work_time_cleaned=work_time_form.cleaned_data,
            workplace_formset=workplace_formset,
            leave_settings_form=leave_settings_form,
        )
        messages.success(request, "Zaměstnanec byl vytvořen.")
        return redirect("employee_detail", pk=employee.pk)
    return render(
        request,
        "employees/form.html",
        _employee_form_context(
            title="Nový zaměstnanec",
            form=form,
            employment_form=employment_form,
            qualification_formset=qualification_formset,
            work_time_form=work_time_form,
            workplace_formset=workplace_formset,
            employee=None,
            leave_settings_form=leave_settings_form,
        ),
    )


@staff_required
@require_http_methods(["GET", "POST"])
def employee_edit(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    current = _employment_for_form(employee)
    form = EmployeeForm(request.POST or None, instance=employee)
    employment_form = EmploymentForm(
        request.POST or None,
        instance=current,
        prefix="emp",
    )
    qualification_formset = _qualification_formset(request, employee)
    work_time_form = _work_time_form(request, current)
    workplace_formset = _workplace_formset(request, employee)
    leave_settings_form = _leave_settings_form(request, current)
    if (
        request.method == "POST"
        and form.is_valid()
        and employment_form.is_valid()
        and qualification_formset.is_valid()
        and work_time_form.is_valid()
        and workplace_formset.is_valid()
        and leave_settings_form.is_valid()
    ):
        employee = form.save(commit=False)
        employment = employment_form.save(commit=False)
        save_employee_bundle(
            user=request.user,
            employee=employee,
            employment=employment,
            qualification_formset=qualification_formset,
            creating=False,
            work_time_cleaned=work_time_form.cleaned_data,
            workplace_formset=workplace_formset,
            leave_settings_form=leave_settings_form,
        )
        messages.success(request, "Zaměstnanec byl uložen.")
        return redirect("employee_detail", pk=employee.pk)
    return render(
        request,
        "employees/form.html",
        _employee_form_context(
            title="Upravit zaměstnance",
            form=form,
            employment_form=employment_form,
            qualification_formset=qualification_formset,
            work_time_form=work_time_form,
            workplace_formset=workplace_formset,
            employee=employee,
            leave_settings_form=leave_settings_form,
        ),
    )


@staff_required
@require_http_methods(["POST"])
def employee_archive(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    archive_employee(user=request.user, employee=employee)
    messages.success(request, "Zaměstnanec byl archivován.")
    return redirect("employee_list")
