from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.core.permissions import staff_required

from .forms import EmployeeWorkplaceForm, WorkplaceForm
from .models import Workplace


@staff_required
@require_http_methods(["GET"])
def workplace_list(request):
    q = request.GET.get("q", "").strip()
    show_archived = request.GET.get("archived") == "1"
    workplaces = Workplace.objects.all()
    if not show_archived:
        workplaces = workplaces.filter(is_active=True)
    if q:
        workplaces = workplaces.filter(
            Q(name__icontains=q) | Q(address__icontains=q)
        )
    return render(
        request,
        "workplaces/list.html",
        {
            "title": "Pracoviště",
            "workplaces": workplaces,
            "q": q,
            "show_archived": show_archived,
        },
    )


@staff_required
@require_http_methods(["GET"])
def workplace_detail(request, pk):
    workplace = get_object_or_404(
        Workplace.objects.prefetch_related(
            "employee_assignments__employee"
        ),
        pk=pk,
    )
    return render(
        request,
        "workplaces/detail.html",
        {"title": workplace.name, "workplace": workplace},
    )


@staff_required
@require_http_methods(["GET", "POST"])
def workplace_create(request):
    form = WorkplaceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        workplace = form.save()
        messages.success(request, "Pracoviště bylo vytvořeno.")
        return redirect("workplace_detail", pk=workplace.pk)
    return render(
        request,
        "workplaces/form.html",
        {"title": "Nové pracoviště", "form": form, "workplace": None},
    )


@staff_required
@require_http_methods(["GET", "POST"])
def workplace_edit(request, pk):
    workplace = get_object_or_404(Workplace, pk=pk)
    form = WorkplaceForm(request.POST or None, instance=workplace)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Pracoviště bylo uloženo.")
        return redirect("workplace_detail", pk=workplace.pk)
    return render(
        request,
        "workplaces/form.html",
        {"title": "Upravit pracoviště", "form": form, "workplace": workplace},
    )


@staff_required
@require_http_methods(["POST"])
def workplace_archive(request, pk):
    workplace = get_object_or_404(Workplace, pk=pk)
    workplace.is_active = False
    workplace.save(update_fields=["is_active", "updated_at"])
    messages.success(request, "Pracoviště bylo archivováno.")
    return redirect("workplace_list")


@staff_required
@require_http_methods(["GET", "POST"])
def assignment_create(request, pk):
    workplace = get_object_or_404(Workplace, pk=pk)
    form = EmployeeWorkplaceForm(
        request.POST or None,
        initial={"workplace": workplace.pk},
    )
    form.fields["workplace"].disabled = True
    if request.method == "POST":
        # disabled field is not posted; bind workplace manually
        data = request.POST.copy()
        data["workplace"] = str(workplace.pk)
        form = EmployeeWorkplaceForm(data)
        if form.is_valid():
            form.save()
            messages.success(request, "Přiřazení bylo uloženo.")
            return redirect("workplace_detail", pk=workplace.pk)
    return render(
        request,
        "workplaces/assignment_form.html",
        {
            "title": "Přiřadit zaměstnance",
            "form": form,
            "workplace": workplace,
        },
    )
