"""Služby šablon a uložených Word dokumentů."""

from __future__ import annotations

from datetime import date

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import AuditEvent
from apps.core.version import APP_NAME, __version__
from apps.employees.models import (
    Employee,
    EmployeeQualification,
    QualificationType,
    WorkTimeProfile,
)
from apps.technika.models import Vehicle, VehicleDocument, VehicleDocumentType
from apps.workplaces.models import EmployeeWorkplace

from .merge import (
    append_placeholder_token,
    build_placeholders_csv,
    create_blank_docx_bytes,
    create_universal_template_bytes,
    replace_placeholders,
    validate_placeholders_in_docx,
)
from .models import DocumentTemplate, DocumentTemplateVersion, StoredDocument
from .placeholders import (
    SCOPE_COMMON,
    get_placeholder,
)

UNIVERSAL_EMPLOYEE_NAME = "Univerzální – zaměstnanec"
UNIVERSAL_VEHICLE_NAME = "Univerzální – vozidlo"


def _audit(user, operation: str, obj, detail: str = "") -> None:
    AuditEvent.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        operation=operation,
        object_type=obj.__class__.__name__,
        object_id=str(obj.pk),
        detail=detail,
    )


def _format_date(value: date | None) -> str:
    if value is None:
        return ""
    return value.strftime("%d.%m.%Y")


def _minutes_label(minutes: int | None) -> str:
    if minutes is None:
        return ""
    hours, mins = minutes // 60, minutes % 60
    return f"{hours}:{mins:02d}" if mins else f"{hours}"


def _issuer_label(user: AbstractBaseUser) -> str:
    full = (user.get_full_name() or "").strip()
    if full:
        return full
    return getattr(user, "username", "") or ""


def _common_values(user: AbstractBaseUser) -> dict[str, str]:
    now = timezone.localtime()
    return {
        "dnes": now.strftime("%d.%m.%Y"),
        "cas": now.strftime("%H:%M"),
        "datum_cas": now.strftime("%d.%m.%Y %H:%M"),
        "vystavil": _issuer_label(user),
        "vystavil_uzivatel": getattr(user, "username", "") or "",
        "aplikace": APP_NAME,
        "verze_aplikace": __version__,
    }


def _current_workplaces(employee: Employee):
    today = timezone.localdate()
    return list(
        EmployeeWorkplace.objects.filter(employee=employee)
        .filter(valid_from__lte=today)
        .filter(
            models_q_valid_to(today)
        )
        .select_related("workplace")
        .order_by("-valid_from")
    )


def models_q_valid_to(today):
    from django.db.models import Q

    return Q(valid_to__isnull=True) | Q(valid_to__gte=today)


def build_employee_values(employee: Employee, user: AbstractBaseUser) -> dict[str, str]:
    employment = employee.current_employment
    profile = None
    if employment is not None:
        profile = (
            WorkTimeProfile.objects.filter(employment=employment, is_active=True)
            .order_by("-valid_from")
            .first()
        )
    workplaces = _current_workplaces(employee)
    primary = workplaces[0].workplace if workplaces else None
    values = {
        **_common_values(user),
        "zamestnanec.jmeno": employee.first_name or "",
        "zamestnanec.prijmeni": employee.last_name or "",
        "zamestnanec.cele_jmeno": employee.full_name,
        "zamestnanec.interni_cislo": employee.internal_number or "",
        "zamestnanec.funkce": employee.job_title or "",
        "zamestnanec.telefon": employee.phone or "",
        "zamestnanec.email": employee.email or "",
        "zamestnanec.pracovni_kontakt": employee.work_contact or "",
        "zamestnanec.poznamka": employee.notes or "",
        "zamestnanec.stav": "aktivní" if employee.is_active else "archivovaný",
        "zamestnanec.den_nastupu": _format_date(
            employment.started_on if employment else None
        ),
        "zamestnanec.den_ukonceni": _format_date(
            employment.ended_on if employment else None
        ),
        "zamestnanec.mzdove_cislo": (
            (employment.payroll_number if employment else "") or ""
        ),
        "zamestnanec.druh_vztahu": (
            employment.get_relation_type_display() if employment else ""
        ),
        "zamestnanec.rezim_odmenovani": (
            employment.get_pay_regime_display() if employment else ""
        ),
        "zamestnanec.funkce_ve_vztahu": (
            (employment.job_title if employment else "") or ""
        ),
        "zamestnanec.uvazek": _minutes_label(
            profile.agreed_weekly_minutes if profile else None
        ),
        "zamestnanec.stanovena_tydenni": _minutes_label(
            profile.statutory_weekly_minutes if profile else None
        ),
        "zamestnanec.rezim_rozvrhu": (
            profile.get_regime_display() if profile else ""
        ),
        "zamestnanec.rozvrzeni": (
            profile.get_distribution_display() if profile else ""
        ),
        "zamestnanec.platnost_uvazku_od": _format_date(
            profile.valid_from if profile else None
        ),
        "zamestnanec.platnost_uvazku_do": _format_date(
            profile.valid_to if profile else None
        ),
        "pracoviste.nazev": primary.name if primary else "",
        "pracoviste.typ": (
            primary.get_workplace_type_display() if primary else ""
        ),
        "pracoviste.adresa": (primary.address if primary else "") or "",
        "pracoviste.seznam": ", ".join(
            item.workplace.name for item in workplaces
        ),
    }
    for qtype in QualificationType.objects.filter(is_active=True):
        qual = (
            EmployeeQualification.objects.filter(
                employee=employee,
                qualification_type=qtype,
                is_active=True,
            )
            .order_by("-valid_until", "-id")
            .first()
        )
        prefix = f"kvalifikace.{qtype.code}"
        values[f"{prefix}.cislo"] = (qual.number if qual else "") or ""
        values[f"{prefix}.skupiny"] = (qual.categories if qual else "") or ""
        values[f"{prefix}.platnost_od"] = _format_date(
            qual.valid_from if qual else None
        )
        values[f"{prefix}.platnost_do"] = _format_date(
            qual.valid_until if qual else None
        )
        values[f"{prefix}.vydal"] = (qual.issued_by if qual else "") or ""
    return values


def _vehicle_doc_map(vehicle: Vehicle) -> dict[str, VehicleDocument]:
    result: dict[str, VehicleDocument] = {}
    docs = (
        VehicleDocument.objects.filter(vehicle=vehicle, is_active=True)
        .select_related("document_type")
        .order_by("document_type__sort_order", "-valid_until", "-id")
    )
    for doc in docs:
        code = doc.document_type.code
        if code not in result:
            result[code] = doc
    return result


def build_vehicle_values(vehicle: Vehicle, user: AbstractBaseUser) -> dict[str, str]:
    responsible = vehicle.responsible
    docs = _vehicle_doc_map(vehicle)
    values = {
        **_common_values(user),
        "vozidlo.spz": vehicle.plate or "",
        "vozidlo.oznaceni": vehicle.name or "",
        "vozidlo.poznamka": vehicle.notes or "",
        "vozidlo.stav": "aktivní" if vehicle.is_active else "archivované",
        "vozidlo.odpovedna_osoba": (
            responsible.full_name if responsible else ""
        ),
        "vozidlo.odpovedna_osoba_telefon": (
            (responsible.phone if responsible else "") or ""
        ),
        "vozidlo.odpovedna_osoba_email": (
            (responsible.email if responsible else "") or ""
        ),
        "vozidlo.odpovedna_osoba_interni_cislo": (
            (responsible.internal_number if responsible else "") or ""
        ),
    }
    for dtype in VehicleDocumentType.objects.filter(is_active=True):
        doc = docs.get(dtype.code)
        prefix = f"doklad.{dtype.code}"
        values[f"{prefix}.cislo"] = (doc.number if doc else "") or ""
        values[f"{prefix}.platnost_od"] = _format_date(
            doc.valid_from if doc else None
        )
        values[f"{prefix}.platnost_do"] = _format_date(
            doc.valid_until if doc else None
        )
        values[f"{prefix}.vydal"] = (doc.issued_by if doc else "") or ""
        values[f"{prefix}.poznamka"] = (doc.notes if doc else "") or ""
    values["vozidlo.stk_platnost_do"] = values.get("doklad.stk.platnost_do", "")
    values["vozidlo.pojistka_platnost_do"] = values.get(
        "doklad.pojistka.platnost_do", ""
    )
    return values


def _safe_filename(base: str) -> str:
    slug = slugify(base, allow_unicode=False) or "dokument"
    return f"{slug}.docx"


def placeholders_csv_for_scope(scope: str) -> bytes:
    return build_placeholders_csv(scope)


@transaction.atomic
def ensure_universal_templates(
    *,
    user=None,
    force_refresh: bool = False,
) -> list[DocumentTemplate]:
    """Založí univerzální šablony; při force_refresh přidá novou verzi s aktuálním katalogem."""
    specs = (
        (
            UNIVERSAL_EMPLOYEE_NAME,
            DocumentTemplate.Scope.EMPLOYEE,
            "Univerzální šablona – zaměstnanec",
        ),
        (
            UNIVERSAL_VEHICLE_NAME,
            DocumentTemplate.Scope.VEHICLE,
            "Univerzální šablona – vozidlo",
        ),
    )
    result: list[DocumentTemplate] = []
    for name, scope, heading in specs:
        template, created = DocumentTemplate.objects.get_or_create(
            name=name,
            defaults={"scope": scope, "is_active": True},
        )
        if template.scope != scope or not template.is_active:
            template.scope = scope
            template.is_active = True
            template.save(update_fields=["scope", "is_active", "updated_at"])
        last = template.versions.order_by("-version_number").first()
        if last is not None and not created and not force_refresh:
            result.append(template)
            continue
        content = create_universal_template_bytes(scope, title=heading)
        next_number = 1 if last is None else last.version_number + 1
        version = DocumentTemplateVersion(
            template=template,
            version_number=next_number,
            uploaded_by=(
                user
                if user and getattr(user, "is_authenticated", False)
                else None
            ),
            notes="Univerzální šablona (MERGEFIELD)",
        )
        version.file.save(
            _safe_filename(f"{name}-v{next_number}"),
            ContentFile(content),
            save=False,
        )
        version.full_clean()
        version.save()
        template.save(update_fields=["updated_at"])
        result.append(template)
    return result


@transaction.atomic
def create_template(
    *,
    user: AbstractBaseUser,
    name: str,
    scope: str,
    uploaded_file=None,
) -> DocumentTemplate:
    template = DocumentTemplate(name=name.strip(), scope=scope, is_active=True)
    template.full_clean()
    template.save()
    if uploaded_file is not None:
        content = uploaded_file.read()
        unknown = validate_placeholders_in_docx(content, scope)
        if unknown:
            raise ValidationError(
                "Neznámé placeholdery: " + ", ".join(unknown)
            )
        filename = _safe_filename(name)
    else:
        content = create_blank_docx_bytes()
        filename = _safe_filename(name)
    version = DocumentTemplateVersion(
        template=template,
        version_number=1,
        uploaded_by=user if getattr(user, "is_authenticated", False) else None,
    )
    version.file.save(filename, ContentFile(content), save=False)
    version.full_clean()
    version.save()
    _audit(user, "document_template_create", template, detail=scope)
    return template


@transaction.atomic
def upload_template_version(
    *,
    user: AbstractBaseUser,
    template: DocumentTemplate,
    uploaded_file,
    notes: str = "",
) -> DocumentTemplateVersion:
    content = uploaded_file.read()
    unknown = validate_placeholders_in_docx(content, template.scope)
    if unknown:
        raise ValidationError("Neznámé placeholdery: " + ", ".join(unknown))
    last = template.versions.order_by("-version_number").first()
    next_number = 1 if last is None else last.version_number + 1
    version = DocumentTemplateVersion(
        template=template,
        version_number=next_number,
        uploaded_by=user if getattr(user, "is_authenticated", False) else None,
        notes=(notes or "").strip(),
    )
    version.file.save(
        _safe_filename(f"{template.name}-v{next_number}"),
        ContentFile(content),
        save=False,
    )
    version.full_clean()
    version.save()
    template.save(update_fields=["updated_at"])
    _audit(
        user,
        "document_template_version",
        template,
        detail=f"v{next_number}",
    )
    return version


@transaction.atomic
def append_placeholder_to_template(
    *,
    user: AbstractBaseUser,
    template: DocumentTemplate,
    placeholder_key: str,
) -> DocumentTemplateVersion:
    definition = get_placeholder(placeholder_key, scope=template.scope)
    if definition is None:
        raise ValidationError("Neznámý placeholder.")
    if (
        template.scope not in definition.scopes
        and SCOPE_COMMON not in definition.scopes
    ):
        raise ValidationError("Placeholder nepatří k okruhu této šablony.")
    current = template.current_version
    if current is None:
        raise ValidationError("Šablona nemá žádnou verzi.")
    content = append_placeholder_token(
        current.file,
        placeholder_key,
        display_label=definition.label,
        help_text=definition.help_text or definition.label,
    )
    last = template.versions.order_by("-version_number").first()
    next_number = last.version_number + 1
    version = DocumentTemplateVersion(
        template=template,
        version_number=next_number,
        uploaded_by=user if getattr(user, "is_authenticated", False) else None,
        notes=f"Vložen MERGEFIELD {placeholder_key}",
    )
    version.file.save(
        _safe_filename(f"{template.name}-v{next_number}"),
        ContentFile(content),
        save=False,
    )
    version.full_clean()
    version.save()
    template.save(update_fields=["updated_at"])
    _audit(
        user,
        "document_template_placeholder",
        template,
        detail=placeholder_key,
    )
    return version


@transaction.atomic
def generate_from_template(
    *,
    user: AbstractBaseUser,
    template: DocumentTemplate,
    employee: Employee | None = None,
    vehicle: Vehicle | None = None,
    title: str = "",
) -> StoredDocument:
    if template.scope == DocumentTemplate.Scope.EMPLOYEE:
        if employee is None or vehicle is not None:
            raise ValidationError("Šablona vyžaduje zaměstnance.")
        values = build_employee_values(employee, user)
    elif template.scope == DocumentTemplate.Scope.VEHICLE:
        if vehicle is None or employee is not None:
            raise ValidationError("Šablona vyžaduje vozidlo.")
        values = build_vehicle_values(vehicle, user)
    else:
        raise ValidationError("Neplatný okruh šablony.")
    version = template.current_version
    if version is None:
        raise ValidationError("Šablona nemá žádnou verzi.")
    data, missing = replace_placeholders(version.file, values)
    label = title.strip() or f"{template.name} – {timezone.localdate():%d.%m.%Y}"
    stored = StoredDocument(
        template_version=version,
        employee=employee,
        vehicle=vehicle,
        title=label,
        created_by=user if getattr(user, "is_authenticated", False) else None,
        missing_placeholders="\n".join(missing),
        is_active=True,
    )
    stored.file.save(_safe_filename(label), ContentFile(data), save=False)
    stored.full_clean()
    stored.save()
    _audit(user, "document_generate", stored, detail=template.name)
    return stored


@transaction.atomic
def upload_stored_document(
    *,
    user: AbstractBaseUser,
    uploaded_file,
    title: str,
    employee: Employee | None = None,
    vehicle: Vehicle | None = None,
    notes: str = "",
) -> StoredDocument:
    name = (uploaded_file.name or "").lower()
    if not name.endswith(".docx"):
        raise ValidationError("Povoleny jsou jen soubory .docx.")
    content = uploaded_file.read()
    label = title.strip() or uploaded_file.name or "Dokument"
    stored = StoredDocument(
        template_version=None,
        employee=employee,
        vehicle=vehicle,
        title=label,
        created_by=user if getattr(user, "is_authenticated", False) else None,
        notes=(notes or "").strip(),
        is_active=True,
    )
    stored.file.save(_safe_filename(label), ContentFile(content), save=False)
    stored.full_clean()
    stored.save()
    _audit(user, "document_upload", stored, detail=label)
    return stored


@transaction.atomic
def deactivate_template(
    *,
    user: AbstractBaseUser,
    template: DocumentTemplate,
) -> DocumentTemplate:
    """Deaktivuje šablonu (včetně univerzálních — lze znovu obnovit)."""
    template.is_active = False
    template.save(update_fields=["is_active", "updated_at"])
    _audit(user, "document_template_deactivate", template, detail=template.name)
    return template


@transaction.atomic
def activate_template(
    *,
    user: AbstractBaseUser,
    template: DocumentTemplate,
) -> DocumentTemplate:
    template.is_active = True
    template.save(update_fields=["is_active", "updated_at"])
    _audit(user, "document_template_activate", template, detail=template.name)
    return template


@transaction.atomic
def archive_stored_document(
    *,
    user: AbstractBaseUser,
    document: StoredDocument,
) -> StoredDocument:
    document.is_active = False
    document.save(update_fields=["is_active"])
    _audit(user, "document_archive", document, detail=document.title)
    return document


@transaction.atomic
def delete_stored_document(
    *,
    user: AbstractBaseUser,
    document: StoredDocument,
) -> None:
    """Natrvalo smaže uložený dokument včetně souboru v media."""
    title = document.title
    _audit(user, "document_delete", document, detail=title)
    if document.file:
        document.file.delete(save=False)
    document.delete()


def list_documents_for_employee(employee: Employee) -> list[StoredDocument]:
    return list(
        StoredDocument.objects.filter(
            employee=employee, is_active=True
        ).select_related("template_version__template", "created_by")
    )


def list_documents_for_vehicle(vehicle: Vehicle) -> list[StoredDocument]:
    return list(
        StoredDocument.objects.filter(
            vehicle=vehicle, is_active=True
        ).select_related("template_version__template", "created_by")
    )
