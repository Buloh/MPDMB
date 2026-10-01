"""Word šablony a uložené dokumenty zaměstnanců / techniky."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def template_upload_to(instance, filename: str) -> str:
    return f"documents/templates/{instance.template_id}/{filename}"


def stored_upload_to(instance, filename: str) -> str:
    return f"documents/stored/{filename}"


class DocumentTemplate(models.Model):
    class Scope(models.TextChoices):
        EMPLOYEE = "zamestnanec", "Zaměstnanec"
        VEHICLE = "vozidlo", "Vozidlo"

    name = models.CharField("název", max_length=160)
    scope = models.CharField(
        "okruh",
        max_length=16,
        choices=Scope.choices,
        db_index=True,
    )
    is_active = models.BooleanField("aktivní", default=True, db_index=True)
    created_at = models.DateTimeField("vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        verbose_name = "šablona dokumentu"
        verbose_name_plural = "šablony dokumentů"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def current_version(self) -> DocumentTemplateVersion | None:
        cache = getattr(self, "_prefetched_objects_cache", None)
        if cache is not None and "versions" in cache:
            versions = list(self.versions.all())
            if not versions:
                return None
            return max(versions, key=lambda item: item.version_number)
        return self.versions.order_by("-version_number").first()


class DocumentTemplateVersion(models.Model):
    template = models.ForeignKey(
        DocumentTemplate,
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name="šablona",
    )
    version_number = models.PositiveIntegerField("číslo verze")
    file = models.FileField("soubor", upload_to=template_upload_to)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_document_template_versions",
        verbose_name="nahrál",
    )
    created_at = models.DateTimeField("vytvořeno", auto_now_add=True)
    notes = models.CharField("poznámka", max_length=255, blank=True)

    class Meta:
        verbose_name = "verze šablony"
        verbose_name_plural = "verze šablon"
        ordering = ["-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "version_number"],
                name="documents_template_version_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.template} · v{self.version_number}"


class StoredDocument(models.Model):
    template_version = models.ForeignKey(
        DocumentTemplateVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stored_documents",
        verbose_name="verze šablony",
    )
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stored_documents",
        verbose_name="zaměstnanec",
    )
    vehicle = models.ForeignKey(
        "technika.Vehicle",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stored_documents",
        verbose_name="vozidlo",
    )
    title = models.CharField("název", max_length=200)
    file = models.FileField("soubor", upload_to=stored_upload_to)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_stored_documents",
        verbose_name="vytvořil",
    )
    created_at = models.DateTimeField("vytvořeno", auto_now_add=True)
    is_active = models.BooleanField("aktivní", default=True, db_index=True)
    missing_placeholders = models.TextField(
        "nevyplněné placeholdery",
        blank=True,
        help_text="Seznam tokenů, které zůstaly prázdné při generování.",
    )
    notes = models.CharField("poznámka", max_length=255, blank=True)

    class Meta:
        verbose_name = "uložený dokument"
        verbose_name_plural = "uložené dokumenty"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employee", "is_active"]),
            models.Index(fields=["vehicle", "is_active"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(employee__isnull=False)
                        & models.Q(vehicle__isnull=True)
                    )
                    | (
                        models.Q(employee__isnull=True)
                        & models.Q(vehicle__isnull=False)
                    )
                ),
                name="documents_stored_exactly_one_target",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    def clean(self) -> None:
        super().clean()
        has_employee = self.employee_id is not None
        has_vehicle = self.vehicle_id is not None
        if has_employee == has_vehicle:
            raise ValidationError(
                "Dokument musí být navázán právě na jednoho zaměstnance "
                "nebo jedno vozidlo."
            )

    @property
    def target_label(self) -> str:
        if self.employee_id:
            return str(self.employee)
        if self.vehicle_id:
            return str(self.vehicle)
        return "—"
