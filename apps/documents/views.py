"""Views panelu Dokumenty (Word šablony a uložené soubory)."""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.core.dashboard import DashboardTile
from apps.employees.models import Employee
from apps.technika.models import Vehicle

from .access import (
    can_access_documents,
    can_manage_stored_documents,
    can_manage_templates,
    can_read_templates,
    can_view_own_documents,
    can_view_stored_document,
    linked_employee,
)
from .forms import (
    AppendPlaceholderForm,
    DocumentTemplateCreateForm,
    DocumentTemplateVersionForm,
    GenerateDocumentForm,
    UploadStoredDocumentForm,
)
from .models import DocumentTemplate, DocumentTemplateVersion, StoredDocument
from .placeholders import placeholders_for_scope
from .services import (
    activate_template,
    append_placeholder_to_template,
    archive_stored_document,
    create_template,
    deactivate_template,
    delete_stored_document,
    ensure_universal_templates,
    generate_from_template,
    placeholders_csv_for_scope,
    upload_stored_document,
    upload_template_version,
)


def _require_access(user) -> None:
    if not can_access_documents(user):
        raise PermissionDenied("Nemáte oprávnění k dokumentům.")


def _require_templates_manage(user) -> None:
    if not can_manage_templates(user):
        raise PermissionDenied("Nemáte oprávnění spravovat šablony.")


def _require_templates_read(user) -> None:
    if not can_read_templates(user):
        raise PermissionDenied("Nemáte oprávnění číst šablony.")


def _require_stored_manage(user) -> None:
    if not can_manage_stored_documents(user):
        raise PermissionDenied("Nemáte oprávnění spravovat dokumenty.")


def _hub_tiles(user) -> list[DashboardTile]:
    tiles: list[DashboardTile] = []
    if can_manage_templates(user):
        tiles.append(
            DashboardTile(
                key="templates",
                title="Šablony",
                description="Word šablony, placeholdery a verze souborů.",
                icon="documents",
                url_name="document_template_list",
            )
        )
    if can_manage_stored_documents(user):
        tiles.append(
            DashboardTile(
                key="employees",
                title="Zaměstnanci",
                description="Uložené dokumenty navázané na zaměstnance.",
                icon="employees",
                url_name="document_employee_list",
            )
        )
        tiles.append(
            DashboardTile(
                key="vehicles",
                title="Technika",
                description="Uložené dokumenty navázané na vozidla.",
                icon="technika",
                url_name="document_vehicle_list",
            )
        )
    if can_view_own_documents(user) and not can_manage_stored_documents(user):
        tiles.append(
            DashboardTile(
                key="mine",
                title="Moje dokumenty",
                description="Dokumenty uložené u vaší karty zaměstnance.",
                icon="documents",
                url_name="document_my_list",
            )
        )
    return tiles


@require_http_methods(["GET"])
def documents_hub(request):
    _require_access(request.user)
    return render(
        request,
        "documents/hub.html",
        {"title": "Dokumenty", "tiles": _hub_tiles(request.user)},
    )


@require_http_methods(["GET"])
def template_list(request):
    _require_templates_manage(request.user)
    ensure_universal_templates(user=request.user, force_refresh=False)
    templates = DocumentTemplate.objects.prefetch_related("versions").order_by(
        "name"
    )
    show_inactive = request.GET.get("inactive") == "1"
    if not show_inactive:
        templates = templates.filter(is_active=True)
    return render(
        request,
        "documents/template_list.html",
        {
            "title": "Šablony dokumentů",
            "templates": templates,
            "show_inactive": show_inactive,
        },
    )


@require_http_methods(["GET", "POST"])
def template_create(request):
    _require_templates_manage(request.user)
    form = DocumentTemplateCreateForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            template = create_template(
                user=request.user,
                name=form.cleaned_data["name"],
                scope=form.cleaned_data["scope"],
                uploaded_file=form.cleaned_data.get("file"),
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Šablona byla vytvořena.")
            return redirect("document_template_detail", pk=template.pk)
    return render(
        request,
        "documents/template_form.html",
        {"title": "Nová šablona", "form": form},
    )


@require_http_methods(["GET", "POST"])
def template_detail(request, pk):
    _require_templates_manage(request.user)
    template = get_object_or_404(
        DocumentTemplate.objects.prefetch_related("versions"),
        pk=pk,
    )
    version_form = DocumentTemplateVersionForm(prefix="ver")
    append_form = AppendPlaceholderForm(scope=template.scope, prefix="ph")
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "version":
            version_form = DocumentTemplateVersionForm(
                request.POST, request.FILES, prefix="ver"
            )
            if version_form.is_valid():
                try:
                    upload_template_version(
                        user=request.user,
                        template=template,
                        uploaded_file=version_form.cleaned_data["file"],
                        notes=version_form.cleaned_data.get("notes") or "",
                    )
                except ValidationError as exc:
                    version_form.add_error(None, exc)
                else:
                    messages.success(request, "Nová verze šablony byla uložena.")
                    return redirect("document_template_detail", pk=template.pk)
        elif action == "placeholder":
            append_form = AppendPlaceholderForm(
                request.POST, scope=template.scope, prefix="ph"
            )
            if append_form.is_valid():
                try:
                    append_placeholder_to_template(
                        user=request.user,
                        template=template,
                        placeholder_key=append_form.cleaned_data["placeholder_key"],
                    )
                except ValidationError as exc:
                    append_form.add_error(None, exc)
                else:
                    messages.success(
                        request,
                        "Placeholder byl vložen do nové verze šablony.",
                    )
                    return redirect("document_template_detail", pk=template.pk)
        elif action == "refresh_universal":
            ensure_universal_templates(user=request.user, force_refresh=True)
            messages.success(
                request,
                "Univerzální šablony byly obnoveny (nová verze s aktuálním katalogem).",
            )
            return redirect("document_template_detail", pk=template.pk)
        elif action == "deactivate":
            deactivate_template(user=request.user, template=template)
            messages.success(request, "Šablona byla deaktivována.")
            return redirect("document_template_list")
        elif action == "activate":
            activate_template(user=request.user, template=template)
            messages.success(request, "Šablona byla znovu aktivována.")
            return redirect("document_template_detail", pk=template.pk)
    return render(
        request,
        "documents/template_detail.html",
        {
            "title": template.name,
            "template": template,
            "current_version": template.current_version,
            "version_form": version_form,
            "append_form": append_form,
            "placeholder_catalog": placeholders_for_scope(template.scope),
        },
    )


@require_http_methods(["GET"])
def template_download(request, pk):
    _require_templates_read(request.user)
    version = get_object_or_404(DocumentTemplateVersion, pk=pk)
    if not version.file:
        raise Http404("Soubor šablony chybí.")
    return FileResponse(
        version.file.open("rb"),
        as_attachment=True,
        filename=version.file.name.rsplit("/", 1)[-1],
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )


@require_http_methods(["GET"])
def template_csv_download(request, pk):
    """CSV hlaviček polí pro Word Korespondence."""
    _require_templates_read(request.user)
    template = get_object_or_404(DocumentTemplate, pk=pk)
    data = placeholders_csv_for_scope(template.scope)
    filename = f"synera-pole-{template.scope}.csv"
    response = HttpResponse(data, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@require_http_methods(["POST"])
def templates_refresh_universal(request):
    _require_templates_manage(request.user)
    ensure_universal_templates(user=request.user, force_refresh=True)
    messages.success(
        request,
        "Univerzální šablony byly obnoveny (nová verze s aktuálním katalogem).",
    )
    return redirect("document_template_list")


@require_http_methods(["GET"])
def employee_document_list(request):
    _require_stored_manage(request.user)
    q = request.GET.get("q", "").strip()
    show_archived = request.GET.get("archived") == "1"
    docs = StoredDocument.objects.filter(employee__isnull=False).select_related(
        "employee",
        "template_version__template",
        "created_by",
    )
    if not show_archived:
        docs = docs.filter(is_active=True)
    if q:
        docs = docs.filter(
            Q(title__icontains=q)
            | Q(employee__last_name__icontains=q)
            | Q(employee__first_name__icontains=q)
            | Q(employee__internal_number__icontains=q)
        )
    return render(
        request,
        "documents/stored_list.html",
        {
            "title": "Dokumenty zaměstnanců",
            "documents": docs,
            "q": q,
            "show_archived": show_archived,
            "kind": "employee",
        },
    )


@require_http_methods(["GET"])
def vehicle_document_list(request):
    _require_stored_manage(request.user)
    q = request.GET.get("q", "").strip()
    show_archived = request.GET.get("archived") == "1"
    docs = StoredDocument.objects.filter(vehicle__isnull=False).select_related(
        "vehicle",
        "template_version__template",
        "created_by",
    )
    if not show_archived:
        docs = docs.filter(is_active=True)
    if q:
        docs = docs.filter(
            Q(title__icontains=q)
            | Q(vehicle__plate__icontains=q)
            | Q(vehicle__name__icontains=q)
        )
    return render(
        request,
        "documents/stored_list.html",
        {
            "title": "Dokumenty techniky",
            "documents": docs,
            "q": q,
            "show_archived": show_archived,
            "kind": "vehicle",
        },
    )


@require_http_methods(["GET"])
def my_document_list(request):
    _require_access(request.user)
    employee = linked_employee(request.user)
    if employee is None:
        raise PermissionDenied("Nemáte propojenou kartu zaměstnance.")
    if can_manage_stored_documents(request.user):
        return redirect("document_employee_list")
    docs = StoredDocument.objects.filter(
        employee=employee, is_active=True
    ).select_related("template_version__template", "created_by")
    return render(
        request,
        "documents/stored_list.html",
        {
            "title": "Moje dokumenty",
            "documents": docs,
            "q": "",
            "show_archived": False,
            "kind": "mine",
        },
    )


@require_http_methods(["GET", "POST"])
def employee_generate(request, employee_id):
    _require_stored_manage(request.user)
    employee = get_object_or_404(Employee, pk=employee_id)
    form = GenerateDocumentForm(
        request.POST or None,
        scope=DocumentTemplate.Scope.EMPLOYEE,
    )
    upload_form = UploadStoredDocumentForm(prefix="up")
    if request.method == "POST":
        action = request.POST.get("action", "generate")
        if action == "upload":
            upload_form = UploadStoredDocumentForm(
                request.POST, request.FILES, prefix="up"
            )
            if upload_form.is_valid():
                try:
                    upload_stored_document(
                        user=request.user,
                        uploaded_file=upload_form.cleaned_data["file"],
                        title=upload_form.cleaned_data["title"],
                        employee=employee,
                        notes=upload_form.cleaned_data.get("notes") or "",
                    )
                except ValidationError as exc:
                    upload_form.add_error(None, exc)
                else:
                    messages.success(request, "Dokument byl nahrán.")
                    return redirect("employee_detail", pk=employee.pk)
        elif form.is_valid():
            try:
                generate_from_template(
                    user=request.user,
                    template=form.cleaned_data["template"],
                    employee=employee,
                    title=form.cleaned_data.get("title") or "",
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Dokument byl vygenerován.")
                return redirect("employee_detail", pk=employee.pk)
    return render(
        request,
        "documents/generate.html",
        {
            "title": f"Dokument – {employee.full_name}",
            "form": form,
            "upload_form": upload_form,
            "target_label": employee.full_name,
            "back_url_name": "employee_detail",
            "back_pk": employee.pk,
        },
    )


@require_http_methods(["GET", "POST"])
def vehicle_generate(request, vehicle_id):
    _require_stored_manage(request.user)
    vehicle = get_object_or_404(Vehicle, pk=vehicle_id)
    form = GenerateDocumentForm(
        request.POST or None,
        scope=DocumentTemplate.Scope.VEHICLE,
    )
    upload_form = UploadStoredDocumentForm(prefix="up")
    if request.method == "POST":
        action = request.POST.get("action", "generate")
        if action == "upload":
            upload_form = UploadStoredDocumentForm(
                request.POST, request.FILES, prefix="up"
            )
            if upload_form.is_valid():
                try:
                    upload_stored_document(
                        user=request.user,
                        uploaded_file=upload_form.cleaned_data["file"],
                        title=upload_form.cleaned_data["title"],
                        vehicle=vehicle,
                        notes=upload_form.cleaned_data.get("notes") or "",
                    )
                except ValidationError as exc:
                    upload_form.add_error(None, exc)
                else:
                    messages.success(request, "Dokument byl nahrán.")
                    return redirect("vehicle_detail", pk=vehicle.pk)
        elif form.is_valid():
            try:
                generate_from_template(
                    user=request.user,
                    template=form.cleaned_data["template"],
                    vehicle=vehicle,
                    title=form.cleaned_data.get("title") or "",
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Dokument byl vygenerován.")
                return redirect("vehicle_detail", pk=vehicle.pk)
    return render(
        request,
        "documents/generate.html",
        {
            "title": f"Dokument – {vehicle}",
            "form": form,
            "upload_form": upload_form,
            "target_label": str(vehicle),
            "back_url_name": "vehicle_detail",
            "back_pk": vehicle.pk,
        },
    )


@require_http_methods(["GET"])
def stored_download(request, pk):
    _require_access(request.user)
    doc = get_object_or_404(StoredDocument, pk=pk)
    if not can_view_stored_document(request.user, doc):
        raise PermissionDenied("Nemáte oprávnění stáhnout tento dokument.")
    if not doc.file:
        raise Http404("Soubor dokumentu chybí.")
    return FileResponse(
        doc.file.open("rb"),
        as_attachment=True,
        filename=doc.file.name.rsplit("/", 1)[-1],
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )


@require_http_methods(["POST"])
def stored_archive(request, pk):
    _require_stored_manage(request.user)
    doc = get_object_or_404(StoredDocument, pk=pk)
    archive_stored_document(user=request.user, document=doc)
    messages.success(request, "Dokument byl archivován.")
    next_url = request.POST.get("next") or ""
    if next_url.startswith("/"):
        return redirect(next_url)
    if doc.employee_id:
        return redirect("employee_detail", pk=doc.employee_id)
    if doc.vehicle_id:
        return redirect("vehicle_detail", pk=doc.vehicle_id)
    return redirect("documents_hub")


@require_http_methods(["POST"])
def stored_delete(request, pk):
    _require_stored_manage(request.user)
    doc = get_object_or_404(StoredDocument, pk=pk)
    employee_id = doc.employee_id
    vehicle_id = doc.vehicle_id
    delete_stored_document(user=request.user, document=doc)
    messages.success(request, "Dokument byl trvale smazán.")
    next_url = request.POST.get("next") or ""
    if next_url.startswith("/"):
        return redirect(next_url)
    if employee_id:
        return redirect("employee_detail", pk=employee_id)
    if vehicle_id:
        return redirect("vehicle_detail", pk=vehicle_id)
    return redirect("documents_hub")
