"""Evidence vozidel, dokladů a odpovědných osob."""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def normalize_plate(value: str) -> str:
    """SPZ bez mezer, velká písmena."""
    return re.sub(r"\s+", "", (value or "").strip()).upper()


class Vehicle(models.Model):
    plate = models.CharField("SPZ", max_length=16, unique=True, db_index=True)
    name = models.CharField(
        "označení",
        max_length=120,
        blank=True,
        help_text="Volitelný popis (např. dodávka, značka).",
    )
    responsible = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="responsible_vehicles",
        verbose_name="odpovědná osoba",
    )
    is_active = models.BooleanField("aktivní", default=True, db_index=True)
    notes = models.CharField("poznámka", max_length=255, blank=True)
    created_at = models.DateTimeField("vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        verbose_name = "vozidlo"
        verbose_name_plural = "vozidla"
        ordering = ["plate"]

    def __str__(self) -> str:
        if self.name:
            return f"{self.plate} ({self.name})"
        return self.plate

    def clean(self) -> None:
        super().clean()
        self.plate = normalize_plate(self.plate)
        if not self.plate:
            raise ValidationError({"plate": "SPZ je povinná."})

    def save(self, *args, **kwargs):
        self.plate = normalize_plate(self.plate)
        super().save(*args, **kwargs)

    def active_documents(self):
        return self.documents.filter(is_active=True).select_related(
            "document_type"
        )

    @property
    def has_expired_documents(self) -> bool:
        return any(doc.is_expired for doc in self.active_documents())

    @property
    def expired_documents_count(self) -> int:
        return sum(1 for doc in self.active_documents() if doc.is_expired)


class VehicleDocumentType(models.Model):
    code = models.SlugField("kód", max_length=64, unique=True)
    name = models.CharField("název", max_length=120)
    description = models.TextField("popis", blank=True)
    requires_number = models.BooleanField("vyžaduje číslo", default=False)
    is_active = models.BooleanField("aktivní", default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField("pořadí", default=100)
    warn_days_before = models.PositiveSmallIntegerField(
        "upozornit dní před expirací",
        default=30,
        help_text="Kolik dní před koncem platnosti zobrazit varování.",
    )

    class Meta:
        verbose_name = "typ dokladu vozidla"
        verbose_name_plural = "typy dokladů vozidel"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class VehicleDocument(models.Model):
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="vozidlo",
    )
    document_type = models.ForeignKey(
        VehicleDocumentType,
        on_delete=models.PROTECT,
        related_name="vehicle_documents",
        verbose_name="typ",
    )
    number = models.CharField("číslo / evidenční znak", max_length=80, blank=True)
    valid_from = models.DateField("platnost od", null=True, blank=True)
    valid_until = models.DateField(
        "platnost do",
        null=True,
        blank=True,
        help_text="Prázdné = bez expirace.",
    )
    issued_by = models.CharField("vydal", max_length=160, blank=True)
    notes = models.CharField("poznámka", max_length=255, blank=True)
    is_active = models.BooleanField("aktivní", default=True, db_index=True)
    created_at = models.DateTimeField("vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        verbose_name = "doklad vozidla"
        verbose_name_plural = "doklady vozidel"
        ordering = ["document_type__sort_order", "document_type__name"]
        indexes = [
            models.Index(fields=["vehicle", "document_type"]),
            models.Index(fields=["valid_until"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(valid_from__isnull=True)
                    | models.Q(valid_until__isnull=True)
                    | models.Q(valid_until__gte=models.F("valid_from"))
                ),
                name="vehicle_document_valid_until_after_from",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.vehicle} · {self.document_type}"

    def clean(self) -> None:
        super().clean()
        if (
            self.valid_from
            and self.valid_until
            and self.valid_until < self.valid_from
        ):
            raise ValidationError(
                {"valid_until": "Platnost do nesmí být dříve než platnost od."}
            )
        dtype = self.document_type
        if dtype and dtype.requires_number and not (self.number or "").strip():
            raise ValidationError({"number": "Tento typ vyžaduje číslo."})

    @property
    def is_expired(self) -> bool:
        if not self.is_active or not self.valid_until:
            return False
        return self.valid_until < timezone.localdate()

    @property
    def days_until_expiry(self) -> int | None:
        if not self.valid_until:
            return None
        return (self.valid_until - timezone.localdate()).days

    @property
    def is_expiring_soon(self) -> bool:
        if self.is_expired or not self.valid_until or not self.is_active:
            return False
        warn = self.document_type.warn_days_before
        days = self.days_until_expiry
        return days is not None and 0 <= days <= warn
