"""Evidence zaměstnanců (oddělená od přihlašovacího účtu)."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Employee(models.Model):
    first_name = models.CharField("jméno", max_length=100)
    last_name = models.CharField("příjmení", max_length=100)
    internal_number = models.CharField(
        "interní číslo",
        max_length=32,
        unique=True,
    )
    job_title = models.CharField("funkce", max_length=120, blank=True)
    is_active = models.BooleanField("aktivní", default=True, db_index=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_profile",
        verbose_name="účet",
    )
    work_contact = models.CharField(
        "pracovní kontakt",
        max_length=200,
        blank=True,
        help_text="Volitelné, jen podle potřeby.",
    )
    phone = models.CharField("telefon", max_length=40, blank=True)
    email = models.EmailField("e-mail", blank=True)
    notes = models.TextField("poznámka", blank=True)
    created_at = models.DateTimeField("vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        verbose_name = "zaměstnanec"
        verbose_name_plural = "zaměstnanci"
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        return f"{self.last_name} {self.first_name} ({self.internal_number})"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def current_employment(self) -> Employment | None:
        today = timezone.localdate()
        cache = getattr(self, "_prefetched_objects_cache", None)
        if cache is not None and "employments" in cache:
            candidates = [
                item
                for item in self.employments.all()
                if item.is_active
                and (item.ended_on is None or item.ended_on >= today)
            ]
            candidates.sort(key=lambda item: item.started_on, reverse=True)
            return candidates[0] if candidates else None
        return (
            self.employments.filter(is_active=True)
            .filter(models.Q(ended_on__isnull=True) | models.Q(ended_on__gte=today))
            .order_by("-started_on")
            .first()
        )

    def active_qualifications(self):
        cache = getattr(self, "_prefetched_objects_cache", None)
        if cache is not None and "qualifications" in cache:
            return [item for item in self.qualifications.all() if item.is_active]
        return list(self.qualifications.filter(is_active=True))

    @property
    def has_expired_qualifications(self) -> bool:
        return any(item.is_expired for item in self.active_qualifications())

    @property
    def expired_qualifications_count(self) -> int:
        return sum(1 for item in self.active_qualifications() if item.is_expired)


class Employment(models.Model):
    class RelationType(models.TextChoices):
        EMPLOYMENT = "PP", "Pracovní poměr"
        AGREEMENT_WORK = "DPP", "Dohoda o provedení práce"
        AGREEMENT_ACTIVITY = "DPČ", "Dohoda o pracovní činnosti"

    class PayRegime(models.TextChoices):
        WAGE = "mzda", "Mzda"
        SALARY = "plat", "Plat"

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="employments",
        verbose_name="zaměstnanec",
    )
    relation_type = models.CharField(
        "druh vztahu",
        max_length=8,
        choices=RelationType.choices,
        default=RelationType.EMPLOYMENT,
    )
    started_on = models.DateField("den nástupu")
    ended_on = models.DateField("den ukončení", null=True, blank=True)
    payroll_number = models.CharField(
        "mzdové číslo",
        max_length=32,
        blank=True,
        help_text="Ukládejte jako text včetně počátečních nul.",
    )
    pay_regime = models.CharField(
        "režim odměňování",
        max_length=8,
        choices=PayRegime.choices,
        default=PayRegime.WAGE,
    )
    job_title = models.CharField("funkce ve vztahu", max_length=120, blank=True)
    is_active = models.BooleanField("aktivní vztah", default=True, db_index=True)
    created_at = models.DateTimeField("vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        verbose_name = "pracovní vztah"
        verbose_name_plural = "pracovní vztahy"
        ordering = ["-started_on"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(ended_on__isnull=True)
                    | models.Q(ended_on__gte=models.F("started_on"))
                ),
                name="employment_ended_on_after_started_on",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee} · {self.get_relation_type_display()} od {self.started_on}"

    def clean(self) -> None:
        super().clean()
        if self.ended_on and self.started_on and self.ended_on < self.started_on:
            raise ValidationError(
                {"ended_on": "Den ukončení nesmí být dříve než den nástupu."}
            )

    @property
    def is_unsupported_for_payroll_export(self) -> bool:
        return self.relation_type in {
            self.RelationType.AGREEMENT_WORK,
            self.RelationType.AGREEMENT_ACTIVITY,
        }


class WorkTimePreset(models.Model):
    """Adminem spravovaná předvolba týdenního úvazku (např. 40 / 37,5 h)."""

    name = models.CharField("název", max_length=80)
    weekly_minutes = models.PositiveIntegerField(
        "týdenní doba (min)",
        help_text="Např. 40 h = 2400, 38,75 h = 2325, 37,5 h = 2250.",
    )
    sort_order = models.PositiveSmallIntegerField("pořadí", default=100)
    is_active = models.BooleanField("aktivní", default=True, db_index=True)

    class Meta:
        verbose_name = "předvolba úvazku"
        verbose_name_plural = "předvolby úvazku"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        hours = self.weekly_minutes // 60
        mins = self.weekly_minutes % 60
        label = f"{hours}:{mins:02d}" if mins else f"{hours}"
        return f"{self.name} ({label} h)"

    @property
    def hours_label(self) -> str:
        hours = self.weekly_minutes // 60
        mins = self.weekly_minutes % 60
        if mins:
            return f"{hours}:{mins:02d}"
        return f"{hours}"


class WorkTimeProfile(models.Model):
    class Regime(models.TextChoices):
        SINGLE = "single", "Jednosměnný"
        TWO = "two", "Dvousměnný"
        MULTI = "multi", "Vícesměnný"
        CONTINUOUS = "continuous", "Nepřetržitý"

    class Distribution(models.TextChoices):
        EVEN = "even", "Rovnoměrné"
        UNEVEN = "uneven", "Nerovnoměrné"

    employment = models.ForeignKey(
        Employment,
        on_delete=models.CASCADE,
        related_name="work_time_profiles",
        verbose_name="pracovní vztah",
    )
    valid_from = models.DateField("platnost od")
    valid_to = models.DateField("platnost do", null=True, blank=True)
    statutory_weekly_minutes = models.PositiveIntegerField(
        "stanovená týdenní doba (min)",
        default=40 * 60,
        help_text="Např. 40 h = 2400, 37,5 h = 2250.",
    )
    agreed_weekly_minutes = models.PositiveIntegerField(
        "sjednaná týdenní doba (min)",
        default=40 * 60,
    )
    regime = models.CharField(
        "režim",
        max_length=16,
        choices=Regime.choices,
        default=Regime.SINGLE,
    )
    distribution = models.CharField(
        "rozvržení",
        max_length=16,
        choices=Distribution.choices,
        default=Distribution.EVEN,
    )
    is_active = models.BooleanField("aktivní", default=True, db_index=True)

    class Meta:
        verbose_name = "profil pracovní doby"
        verbose_name_plural = "profily pracovní doby"
        ordering = ["-valid_from"]

    def __str__(self) -> str:
        return f"{self.employment} · od {self.valid_from}"

    def covers(self, day):
        if not self.is_active:
            return False
        if day < self.valid_from:
            return False
        if self.valid_to and day > self.valid_to:
            return False
        return True


class BalancingPeriod(models.Model):
    class Kind(models.TextChoices):
        SCHEDULE = "schedule", "Vyrovnání rozvrhu"
        OVERTIME = "overtime", "Vyrovnání přesčasů"

    profile = models.ForeignKey(
        WorkTimeProfile,
        on_delete=models.CASCADE,
        related_name="balancing_periods",
        verbose_name="profil",
    )
    starts_on = models.DateField("začátek")
    ends_on = models.DateField("konec")
    kind = models.CharField(
        "druh",
        max_length=16,
        choices=Kind.choices,
        default=Kind.SCHEDULE,
    )
    target_minutes = models.PositiveIntegerField(
        "cílový fond (min)",
        help_text="Cílové minuty za období. Lze nechat dopočítat ze sjednané týdenní doby.",
    )
    note = models.CharField("poznámka", max_length=255, blank=True)

    class Meta:
        verbose_name = "vyrovnávací období"
        verbose_name_plural = "vyrovnávací období"
        ordering = ["-starts_on"]

    def __str__(self) -> str:
        hours = self.target_minutes // 60
        mins = self.target_minutes % 60
        target = f"{hours}:{mins:02d}" if mins else f"{hours}"
        emp = self.profile.employment.employee
        return (
            f"{emp.last_name} {emp.first_name} · "
            f"{self.starts_on:%d.%m.%Y}–{self.ends_on:%d.%m.%Y} · "
            f"{self.get_kind_display()} · cíl {target} h"
        )

    def clean(self) -> None:
        super().clean()
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError(
                {"ends_on": "Konec období musí být stejný nebo pozdější než začátek."}
            )

    @staticmethod
    def compute_target_minutes(agreed_weekly_minutes: int, starts_on, ends_on) -> int:
        days = (ends_on - starts_on).days + 1
        return int(days * agreed_weekly_minutes / 7)

    def covers(self, day) -> bool:
        return self.starts_on <= day <= self.ends_on


class QualificationType(models.Model):
    code = models.SlugField("kód", max_length=64, unique=True)
    name = models.CharField("název", max_length=120)
    description = models.TextField("popis", blank=True)
    requires_number = models.BooleanField("vyžaduje číslo", default=False)
    requires_categories = models.BooleanField(
        "vyžaduje skupiny/kategorie",
        default=False,
        help_text="Např. skupiny řidičského průkazu B, C.",
    )
    is_active = models.BooleanField("aktivní", default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField("pořadí", default=100)
    warn_days_before = models.PositiveSmallIntegerField(
        "upozornit dní před expirací",
        default=30,
        help_text="Kolik dní před koncem platnosti zobrazit varování.",
    )

    class Meta:
        verbose_name = "typ kvalifikace"
        verbose_name_plural = "typy kvalifikací"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class EmployeeQualification(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="qualifications",
        verbose_name="zaměstnanec",
    )
    qualification_type = models.ForeignKey(
        QualificationType,
        on_delete=models.PROTECT,
        related_name="employee_qualifications",
        verbose_name="typ",
    )
    number = models.CharField("číslo / evidenční znak", max_length=80, blank=True)
    categories = models.CharField(
        "skupiny / rozsah",
        max_length=80,
        blank=True,
        help_text="Např. B, C nebo § 6.",
    )
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
        verbose_name = "kvalifikace zaměstnance"
        verbose_name_plural = "kvalifikace zaměstnanců"
        ordering = ["qualification_type__sort_order", "qualification_type__name"]
        indexes = [
            models.Index(fields=["employee", "qualification_type"]),
            models.Index(fields=["valid_until"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(valid_from__isnull=True)
                    | models.Q(valid_until__isnull=True)
                    | models.Q(valid_until__gte=models.F("valid_from"))
                ),
                name="qualification_valid_until_after_from",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee} · {self.qualification_type}"

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
        qtype = self.qualification_type
        if qtype and qtype.requires_number and not self.number.strip():
            raise ValidationError({"number": "Tento typ vyžaduje číslo."})
        if qtype and qtype.requires_categories and not self.categories.strip():
            raise ValidationError({"categories": "Tento typ vyžaduje skupiny."})

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
        warn = self.qualification_type.warn_days_before
        days = self.days_until_expiry
        return days is not None and 0 <= days <= warn
