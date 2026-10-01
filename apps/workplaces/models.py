"""Pracoviště a přiřazení zaměstnanců."""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import models


class Workplace(models.Model):
    class WorkplaceType(models.TextChoices):
        PARKING_HOUSE = "parking_house", "Parkovací dům"
        OFFICE = "office", "Kancelář"
        OTHER = "other", "Jiné"

    name = models.CharField("název", max_length=150)
    workplace_type = models.CharField(
        "typ",
        max_length=32,
        choices=WorkplaceType.choices,
        default=WorkplaceType.PARKING_HOUSE,
    )
    address = models.CharField("adresa", max_length=255, blank=True)
    is_active = models.BooleanField("aktivní", default=True, db_index=True)
    created_at = models.DateTimeField("vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        verbose_name = "pracoviště"
        verbose_name_plural = "pracoviště"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class EmployeeWorkplace(models.Model):
    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="workplace_assignments",
        verbose_name="zaměstnanec",
    )
    workplace = models.ForeignKey(
        Workplace,
        on_delete=models.PROTECT,
        related_name="employee_assignments",
        verbose_name="pracoviště",
    )
    valid_from = models.DateField("platnost od")
    valid_to = models.DateField("platnost do", null=True, blank=True)
    created_at = models.DateTimeField("vytvořeno", auto_now_add=True)

    class Meta:
        verbose_name = "přiřazení k pracovišti"
        verbose_name_plural = "přiřazení k pracovištím"
        ordering = ["-valid_from", "employee_id"]
        indexes = [
            models.Index(fields=["employee", "workplace"]),
            models.Index(fields=["valid_from", "valid_to"]),
        ]

    def __str__(self) -> str:
        return f"{self.employee} → {self.workplace}"

    def clean(self):
        if self.valid_to and self.valid_from and self.valid_to < self.valid_from:
            raise ValidationError(
                {"valid_to": "Datum konce platnosti nesmí být dříve než začátek."}
            )
        if not self.employee_id or not self.valid_from:
            return

        from apps.employees.models import Employment

        employments = Employment.objects.filter(
            employee_id=self.employee_id, is_active=True
        )
        covering = (
            employments.filter(started_on__lte=self.valid_from)
            .filter(
                models.Q(ended_on__isnull=True)
                | models.Q(ended_on__gte=self.valid_from)
            )
            .order_by("-started_on")
            .first()
        )
        if covering is None:
            earliest = employments.order_by("started_on").first()
            if earliest is None:
                raise ValidationError(
                    {
                        "valid_from": (
                            "Nejdříve nastavte den nástupu na kartě zaměstnance."
                        )
                    }
                )
            if self.valid_from < earliest.started_on:
                raise ValidationError(
                    {
                        "valid_from": (
                            "Platnost pracoviště nesmí začínat dříve než den "
                            f"nástupu ({earliest.started_on:%d.%m.%Y})."
                        )
                    }
                )
            raise ValidationError(
                {
                    "valid_from": (
                        "K datu platnosti pracoviště chybí aktivní pracovní vztah."
                    )
                }
            )

        others = EmployeeWorkplace.objects.filter(employee_id=self.employee_id)
        if self.pk:
            others = others.exclude(pk=self.pk)
        new_end = self.valid_to or date.max
        for other in others:
            other_end = other.valid_to or date.max
            if self.valid_from <= other_end and other.valid_from <= new_end:
                raise ValidationError(
                    "Platnost se překrývá s jiným přiřazením pracoviště. "
                    "V jeden den smí být jen jedno pracoviště."
                )
