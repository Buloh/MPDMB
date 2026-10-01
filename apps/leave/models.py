"""Roční plán dovolené (oddělený od docházky a mzdové uzávěrky)."""

from __future__ import annotations

from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class LeavePolicySettings(models.Model):
    """Singleton: výchozí pravidla dovolené (lze vypnout kontroly)."""

    default_weeks_wage = models.PositiveSmallIntegerField(
        "výměra týdnů (mzda)",
        default=4,
        help_text="Zákonné minimum pro mzdový režim (§ 212).",
    )
    default_weeks_salary = models.PositiveSmallIntegerField(
        "výměra týdnů (plat)",
        default=5,
        help_text="Výchozí pro platový režim.",
    )
    carryover_min_weeks_kept = models.PositiveSmallIntegerField(
        "nepřevoditelné týdny",
        default=4,
        help_text="Část nároku, kterou nelze převést (zákonné minimum).",
    )
    continuous_min_days = models.PositiveSmallIntegerField(
        "min. souvislý úsek (pracovní dny)",
        default=14,
        help_text="Počet pracovních dnů Po–Pá (výchozí 14). So/Ne se nepočítají.",
    )
    continuous_count_holidays = models.BooleanField(
        "započítat svátky do souvislého úseku",
        default=False,
        help_text="Pokud vypnuto, svátek v Po–Pá se do délky úseku nepočítá.",
    )
    allow_carryover = models.BooleanField("povolit převod do dalšího roku", default=True)
    enforce_continuous_block = models.BooleanField(
        "vyžadovat souvislý úsek",
        default=False,
        help_text="Při zapnutí nelze schválit blok kratší než min. souvislý úsek.",
    )
    prefer_older_entitlement = models.BooleanField(
        "čerpat nejdřív starší nárok",
        default=True,
    )
    warn_unused_carryover = models.BooleanField(
        "upozornit na nevyčerpaný převod",
        default=True,
    )
    block_overlap_with_work_shifts = models.BooleanField(
        "blokovat překryv se směnou práce",
        default=True,
    )
    allow_half_day = models.BooleanField(
        "povolit půldenní dovolenou",
        default=True,
        help_text="Minimálně ½ směny (§ 218 odst. 6). Lze vypnout globálně.",
    )
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        verbose_name = "pravidla dovolené"
        verbose_name_plural = "pravidla dovolené"

    def __str__(self) -> str:
        return (
            f"Dovolená {self.default_weeks_wage}/{self.default_weeks_salary} týdnů"
        )

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls) -> "LeavePolicySettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class EmployeeLeaveSettings(models.Model):
    """Individuální úprava výměry a kontrol u pracovního vztahu."""

    employment = models.OneToOneField(
        "employees.Employment",
        on_delete=models.CASCADE,
        related_name="leave_settings",
        verbose_name="pracovní vztah",
    )
    extra_weeks = models.PositiveSmallIntegerField(
        "navíc týdnů",
        default=0,
        help_text="Nad rámec výchozí výměry z pravidel.",
    )
    enforce_continuous_block = models.BooleanField(
        "vynutit souvislý úsek",
        null=True,
        blank=True,
        help_text="Prázdné = podle globálních pravidel.",
    )
    allow_carryover = models.BooleanField(
        "povolit převod",
        null=True,
        blank=True,
        help_text="Prázdné = podle globálních pravidel.",
    )
    allow_half_day = models.BooleanField(
        "povolit půldenní dovolenou",
        null=True,
        blank=True,
        help_text="Prázdné = podle globálních pravidel.",
    )
    note = models.CharField("poznámka", max_length=255, blank=True)
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        verbose_name = "nastavení dovolené zaměstnance"
        verbose_name_plural = "nastavení dovolené zaměstnanců"

    def __str__(self) -> str:
        return f"Dovolená · {self.employment}"


class LeaveEntitlement(models.Model):
    """Roční nárok v minutách pro pracovní vztah."""

    employment = models.ForeignKey(
        "employees.Employment",
        on_delete=models.CASCADE,
        related_name="leave_entitlements",
        verbose_name="pracovní vztah",
    )
    year = models.PositiveSmallIntegerField("rok", db_index=True)
    entitled_minutes = models.PositiveIntegerField(
        "nárok odhad (min)",
        default=0,
        help_text="Odhad do konce roku (pro plánování).",
    )
    accrued_minutes = models.PositiveIntegerField(
        "nárok naběhlý (min)",
        default=0,
        help_text="Skutečnost dle odpracovaných násobků týdenní doby (§ 213).",
    )
    carried_in_minutes = models.PositiveIntegerField("převod z minulého roku", default=0)
    planned_minutes = models.PositiveIntegerField("naplánováno (min)", default=0)
    taken_minutes = models.PositiveIntegerField("vyčerpáno (min)", default=0)
    preferred_use_by = models.DateField(
        "ideálně vyčerpat do",
        null=True,
        blank=True,
        help_text="Výchozí 31.12. roku vzniku (§ 218 odst. 1). Lze upravit v adminu.",
    )
    statutory_latest_use_by = models.DateField(
        "nejzazší vyčerpání nároku",
        null=True,
        blank=True,
        help_text="Výchozí 31.12. následujícího roku (§ 218 odst. 3). "
        "U výjimek (např. PN/MD/RD) upravte a zaškrtněte ruční lhůty.",
    )
    deadlines_manual = models.BooleanField(
        "lhůty nastaveny ručně",
        default=False,
        help_text="Zapnuto = systém při obnově nároku lhůty nepřepisuje.",
    )
    must_use_by = models.DateField(
        "vyčerpat převod do",
        null=True,
        blank=True,
        help_text="Jen při převodu z minulého roku (§ 218 odst. 3). "
        "Lhůty vlastního nároku roku jsou výše (ideálně / nejzazší).",
    )
    source_note = models.CharField("zdroj výpočtu", max_length=255, blank=True)
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        verbose_name = "nárok dovolené"
        verbose_name_plural = "nároky dovolené"
        ordering = ["-year", "employment_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["employment", "year"],
                name="leave_entitlement_unique_employment_year",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employment} · {self.year}"

    def default_preferred_use_by(self) -> date:
        return date(self.year, 12, 31)

    def default_statutory_latest_use_by(self) -> date | None:
        if self.entitled_minutes <= 0 and self.accrued_minutes <= 0:
            return None
        return date(self.year + 1, 12, 31)

    def apply_default_deadlines(self) -> None:
        """Nastaví výchozí lhůty nároku roku (§ 218)."""
        self.preferred_use_by = self.default_preferred_use_by()
        self.statutory_latest_use_by = self.default_statutory_latest_use_by()

    @property
    def remaining_minutes(self) -> int:
        """Zůstatek oproti odhadovanému nároku (pro plánování)."""
        used = max(self.planned_minutes, self.taken_minutes)
        return max(0, self.entitled_minutes + self.carried_in_minutes - used)

    @property
    def accrued_remaining_minutes(self) -> int:
        """Zůstatek oproti naběhlému nároku."""
        used = max(self.planned_minutes, self.taken_minutes)
        return max(0, self.accrued_minutes + self.carried_in_minutes - used)

    @property
    def own_year_remaining_minutes(self) -> int:
        """Zůstatek vlastního nároku roku bez převodu (odhad)."""
        used = max(self.planned_minutes, self.taken_minutes)
        after_carry = max(0, used - self.carried_in_minutes)
        return max(0, self.entitled_minutes - after_carry)


class LeavePlan(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Návrh"
        APPROVED = "approved", "Schváleno"
        CANCELLED = "cancelled", "Zrušeno"

    employment = models.ForeignKey(
        "employees.Employment",
        on_delete=models.CASCADE,
        related_name="leave_plans",
        verbose_name="pracovní vztah",
    )
    year = models.PositiveSmallIntegerField("rok", db_index=True)
    starts_on = models.DateField("od")
    ends_on = models.DateField("do")
    total_minutes = models.PositiveIntegerField("celkem minut", default=0)
    portion = models.CharField(
        "část dne",
        max_length=8,
        choices=[
            ("full", "Celý den"),
            ("am", "Dopoledne"),
            ("pm", "Odpoledne"),
        ],
        default="full",
        help_text="Půlden jen u jednodenního bloku.",
    )
    status = models.CharField(
        "stav",
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    note = models.CharField("poznámka", max_length=255, blank=True)
    version = models.PositiveIntegerField("verze", default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_leave_plans",
        verbose_name="vytvořil",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_leave_plans",
        verbose_name="schválil",
    )
    created_at = models.DateTimeField("vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        verbose_name = "plán dovolené"
        verbose_name_plural = "plány dovolené"
        ordering = ["-starts_on", "-id"]
        indexes = [
            models.Index(fields=["employment", "year"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.employment.employee} "
            f"{self.starts_on:%d.%m.%Y}–{self.ends_on:%d.%m.%Y}"
        )

    def clean(self):
        if self.ends_on and self.starts_on and self.ends_on < self.starts_on:
            raise ValidationError({"ends_on": "Konec nesmí být dříve než začátek."})
        if self.starts_on and self.starts_on.year != self.year:
            raise ValidationError({"starts_on": "Začátek musí být ve zvoleném roce."})
        if self.ends_on and self.ends_on.year != self.year:
            raise ValidationError({"ends_on": "Konec musí být ve zvoleném roce."})


class LeavePlanDay(models.Model):
    """Jeden den schváleného plánu s vazbou na směnu v dlouhodobém plánu."""

    class Portion(models.TextChoices):
        FULL = "full", "Celý den"
        AM = "am", "Dopoledne"
        PM = "pm", "Odpoledne"

    plan = models.ForeignKey(
        LeavePlan,
        on_delete=models.CASCADE,
        related_name="days",
        verbose_name="plán",
    )
    day = models.DateField("den", db_index=True)
    minutes = models.PositiveIntegerField("minuty", default=0)
    portion = models.CharField(
        "část dne",
        max_length=8,
        choices=Portion.choices,
        default=Portion.FULL,
    )
    shift = models.ForeignKey(
        "shifts.Shift",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leave_plan_days",
        verbose_name="směna",
    )

    class Meta:
        verbose_name = "den plánu dovolené"
        verbose_name_plural = "dny plánu dovolené"
        ordering = ["day"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "day"],
                name="leave_plan_day_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.day:%d.%m.%Y} · {self.minutes} min"
