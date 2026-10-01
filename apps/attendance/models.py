"""Skutečná docházka (oddělená od plánu směn)."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class AbsenceType(models.Model):
    class AccountingKind(models.TextChoices):
        PAID_LEAVE = "paid_leave", "Placená nepřítomnost"
        SICK = "sick", "Nemoc"
        OTHER = "other", "Ostatní"

    code = models.CharField("kód", max_length=32, unique=True)
    name = models.CharField("název", max_length=80)
    accounting_kind = models.CharField(
        "druh započtení",
        max_length=16,
        choices=AccountingKind.choices,
        default=AccountingKind.PAID_LEAVE,
    )
    is_active = models.BooleanField("aktivní", default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField("pořadí", default=100)

    class Meta:
        verbose_name = "typ absence"
        verbose_name_plural = "typy absencí"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class WorkInterval(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Návrh"
        CONFIRMED = "confirmed", "Potvrzeno"

    employment = models.ForeignKey(
        "employees.Employment",
        on_delete=models.CASCADE,
        related_name="work_intervals",
        verbose_name="pracovní vztah",
    )
    workplace = models.ForeignKey(
        "workplaces.Workplace",
        on_delete=models.PROTECT,
        related_name="work_intervals",
        verbose_name="pracoviště",
    )
    shift = models.ForeignKey(
        "shifts.Shift",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_intervals",
        verbose_name="směna",
    )
    starts_at = models.DateTimeField("začátek")
    ends_at = models.DateTimeField("konec")
    break_minutes = models.PositiveSmallIntegerField(
        "neplacená pauza (min)",
        default=0,
        help_text="Potvrzená pauza; bez fiktivní automatické srážky.",
    )
    status = models.CharField(
        "stav",
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    version = models.PositiveIntegerField("verze", default=1)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_work_intervals",
        verbose_name="potvrdil",
    )
    confirmed_at = models.DateTimeField("potvrzeno", null=True, blank=True)
    note = models.CharField("poznámka", max_length=255, blank=True)
    created_at = models.DateTimeField("vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        verbose_name = "pracovní interval"
        verbose_name_plural = "pracovní intervaly"
        ordering = ["starts_at"]
        indexes = [
            models.Index(fields=["employment", "starts_at"]),
            models.Index(fields=["shift", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="work_interval_ends_after_starts",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employment} · {self.starts_at}–{self.ends_at}"

    def clean(self) -> None:
        super().clean()
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError(
                {"ends_at": "Konec musí být později než začátek."}
            )

    def net_minutes(self) -> int:
        if self.status != self.Status.CONFIRMED:
            return 0
        gross = int((self.ends_at - self.starts_at).total_seconds() // 60)
        return max(0, gross - int(self.break_minutes))


class Absence(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Návrh"
        APPROVED = "approved", "Schváleno"

    employment = models.ForeignKey(
        "employees.Employment",
        on_delete=models.CASCADE,
        related_name="absences",
        verbose_name="pracovní vztah",
    )
    absence_type = models.ForeignKey(
        AbsenceType,
        on_delete=models.PROTECT,
        related_name="absences",
        verbose_name="typ absence",
    )
    shift = models.ForeignKey(
        "shifts.Shift",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="absences",
        verbose_name="směna",
    )
    day = models.DateField("den", db_index=True)
    planned_missed_minutes = models.PositiveIntegerField(
        "zameškané plánované minuty",
        help_text="Odvozeno z publikované směny, ne plošných 8 h.",
    )
    status = models.CharField(
        "stav",
        max_length=16,
        choices=Status.choices,
        default=Status.APPROVED,
        db_index=True,
    )
    note = models.CharField("poznámka", max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_absences",
        verbose_name="zapsal",
    )
    created_at = models.DateTimeField("vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        verbose_name = "absence"
        verbose_name_plural = "absence"
        ordering = ["-day", "-id"]
        indexes = [
            models.Index(fields=["employment", "day"]),
            models.Index(fields=["shift"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["shift"],
                condition=models.Q(shift__isnull=False),
                name="absence_unique_shift",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.absence_type} · {self.day:%d.%m.%Y}"


class MealAllowanceSettings(models.Model):
    """Singleton: prahy čisté práce pro 1. a 2. stravenku za den."""

    min_worked_minutes = models.PositiveIntegerField(
        "1. stravenka od (minuty)",
        default=180,
        help_text="Minimální čistá potvrzená práce v kalendářním dni pro 1. stravenku.",
    )
    second_worked_minutes = models.PositiveIntegerField(
        "2. stravenka od (minuty)",
        null=True,
        blank=True,
        default=720,
        help_text=(
            "Práh pro 2. stravenku ve stejném dni. Prázdné = nejvýše 1 stravenka."
        ),
    )
    is_active = models.BooleanField("aktivní", default=True)
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        verbose_name = "stravné"
        verbose_name_plural = "stravné"

    def __str__(self) -> str:
        first = self.min_worked_minutes / 60
        state = "aktivní" if self.is_active else "vypnuto"
        if self.second_worked_minutes:
            second = self.second_worked_minutes / 60
            return f"Stravné {first:g} h / {second:g} h ({state})"
        return f"Stravné od {first:g} h ({state})"

    def clean(self):
        if self.min_worked_minutes < 1:
            raise ValidationError(
                {"min_worked_minutes": "Zadejte alespoň 1 minutu."}
            )
        if (
            self.second_worked_minutes is not None
            and self.second_worked_minutes <= self.min_worked_minutes
        ):
            raise ValidationError(
                {
                    "second_worked_minutes": (
                        "Práh 2. stravenky musí být větší než práh 1. stravenky."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls) -> "MealAllowanceSettings":
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                "min_worked_minutes": 180,
                "second_worked_minutes": 720,
                "is_active": True,
            },
        )
        return obj
