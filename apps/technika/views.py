"""Views evidence vozidel."""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.core.dashboard import can_manage_directory
from apps.documents.access import can_manage_stored_documents
from apps.documents.services import list_documents_for_vehicle

from .forms import VehicleDocumentFormSet, VehicleForm
from .models import Vehicle, VehicleDocument
from .services import archive_vehicle, save_vehicle_bundle


def _require_directory(user) -> None:
    if not can_manage_directory(user):
        raise PermissionDenied("Nemáte oprávnění spravovat techniku.")


def _document_formset(request, vehicle: Vehicle | None):
    instance = vehicle if vehicle is not None else Vehicle()
    if request.method == "POST":
        return VehicleDocumentFormSet(
            request.POST, instance=instance, prefix="doc"
        )
    return VehicleDocumentFormSet(instance=instance, prefix="doc")


@require_http_methods(["GET"])
def vehicle_list(request):
    _require_directory(request.user)
    q = request.GET.get("q", "").strip()
    show_archived = request.GET.get("archived") == "1"
    vehicles = Vehicle.objects.select_related("responsible").prefetch_related(
        Prefetch(
            "documents",
            queryset=VehicleDocument.objects.filter(is_active=True).select_related(
                "document_type"
            ),
        )
    )
    if not show_archived:
        vehicles = vehicles.filter(is_active=True)
    if q:
        vehicles = vehicles.filter(
            Q(plate__icontains=q)
            | Q(name__icontains=q)
            | Q(responsible__last_name__icontains=q)
            | Q(responsible__first_name__icontains=q)
        )
    return render(
        request,
        "technika/list.html",
        {
            "title": "Technika",
            "vehicles": vehicles,
            "q": q,
            "show_archived": show_archived,
        },
    )


@require_http_methods(["GET"])
def vehicle_detail(request, pk):
    _require_directory(request.user)
    vehicle = get_object_or_404(
        Vehicle.objects.select_related("responsible").prefetch_related(
            Prefetch(
                "documents",
                queryset=VehicleDocument.objects.select_related("document_type"),
            )
        ),
        pk=pk,
    )
    return render(
        request,
        "technika/detail.html",
        {
            "title": str(vehicle),
            "vehicle": vehicle,
            "stored_documents": list_documents_for_vehicle(vehicle),
            "can_manage_stored_docs": can_manage_stored_documents(request.user),
        },
    )


@require_http_methods(["GET", "POST"])
def vehicle_create(request):
    _require_directory(request.user)
    form = VehicleForm(request.POST or None)
    document_formset = _document_formset(request, None)
    if request.method == "POST" and form.is_valid() and document_formset.is_valid():
        vehicle = form.save(commit=False)
        save_vehicle_bundle(
            user=request.user,
            vehicle=vehicle,
            document_formset=document_formset,
            creating=True,
        )
        messages.success(request, "Vozidlo bylo vytvořeno.")
        return redirect("vehicle_detail", pk=vehicle.pk)
    return render(
        request,
        "technika/form.html",
        {
            "title": "Nové vozidlo",
            "form": form,
            "document_formset": document_formset,
            "vehicle": None,
        },
    )


@require_http_methods(["GET", "POST"])
def vehicle_edit(request, pk):
    _require_directory(request.user)
    vehicle = get_object_or_404(Vehicle, pk=pk)
    form = VehicleForm(request.POST or None, instance=vehicle)
    document_formset = _document_formset(request, vehicle)
    if request.method == "POST" and form.is_valid() and document_formset.is_valid():
        vehicle = form.save(commit=False)
        save_vehicle_bundle(
            user=request.user,
            vehicle=vehicle,
            document_formset=document_formset,
            creating=False,
        )
        messages.success(request, "Vozidlo bylo uloženo.")
        return redirect("vehicle_detail", pk=vehicle.pk)
    return render(
        request,
        "technika/form.html",
        {
            "title": "Upravit vozidlo",
            "form": form,
            "document_formset": document_formset,
            "vehicle": vehicle,
        },
    )


@require_http_methods(["POST"])
def vehicle_archive(request, pk):
    _require_directory(request.user)
    vehicle = get_object_or_404(Vehicle, pk=pk)
    archive_vehicle(user=request.user, vehicle=vehicle)
    messages.success(request, "Vozidlo bylo archivováno.")
    return redirect("vehicle_list")
