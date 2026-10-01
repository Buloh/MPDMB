"""Plán směn (oddělený od skutečné docházky)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class ShiftType(models.Model):
    class Kind(models.TextChoices):
        WORK = "work", "Práce"
        STANDBY = "standby", "Pohotovost"
        LEAVE = "leave", "Dovolená"

    code = models.CharField("symbol", max_length=8, unique=True)
    name = models.CharField("název", max_length=80)
    kind = models.CharField(
        "druh",
        max_length=16,
        choices=Kind.choices,
        default=Kind.WORK,
        db_index=True,
        help_text=(
            "Pohotovost se nezapočítává do odpracovaných hodin (§ 140). "
            "Dovolená patří do dlouhodobého plánu, ne do čisté práce."
        ),
    )
    start_time = models.TimeField("začátek")
    end_time = models.TimeField("konec")
    break_minutes = models.PositiveSmallIntegerField(
        "neplacená pauza (min)",
        default=0,
    )
    counts_as_work = models.BooleanField("započítat do plánu", default=True)
    applies_on_holiday = models.BooleanField(
        "povoleno ve svátek",
        default=True,
    )
    is_active = models.BooleanField("aktivní", default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField("pořadí", default=100)

    class Meta:
        verbose_name = "typ směny"
        verbose_name_plural = "typy směn"
        ordering = ["sort_order", "code"]

    def __str__(self) -> str:
        return f"{self.code} – {self.name}"

    @property
    def crosses_midnight(self) -> bool:
        return self.end_time <= self.start_time

    def net_minutes(self) -> int:
        start = datetime.combine(datetime.min.date(), self.start_time)
        end = datetime.combine(datetime.min.date(), self.end_time)
        if self.crosses_midnight:
            end += timedelta(days=1)
        gross = int((end - start).total_seconds() // 60)
        return max(0, gross - int(self.break_minutes))

    @property
    def net_hours_label(self) -> str:
        minutes = self.net_minutes()
        hours = minutes // 60
        mins = minutes % 60
        if mins:
            return f"{hours}:{mins:02d}"
        return f"{hours}:00"

    def bounds_for_date(self, day):
        """Vrátí (starts_at, ends_at) timezone-aware pro daný kalendářní den."""
        tz = timezone.get_current_timezone()
        start_naive = datetime.combine(day, self.start_time)
        end_day = day + timedelta(days=1) if self.crosses_midnight else day
        end_naive = datetime.combine(end_day, self.end_time)
        return (
            timezone.make_aware(start_naive, tz),
            timezone.make_aware(end_naive, tz),
        )


class Shift(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Návrh"
        PUBLISHED = "published", "Publikováno"
        CANCELLED = "cancelled", "Zrušeno"

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="shifts",
        verbose_name="zaměstnanec",
    )
    workplace = models.ForeignKey(
        "workplaces.Workplace",
        on_delete=models.PROTECT,
        related_name="shifts",
        verbose_name="pracoviště",
    )
    shift_type = models.ForeignKey(
        ShiftType,
        on_delete=models.PROTECT,
        related_name="shifts",
        verbose_name="typ směny",
        null=True,
        blank=True,
    )
    starts_at = models.DateTimeField("začátek")
    ends_at = models.DateTimeField("konec")
    status = models.CharField(
        "stav",
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    note = models.CharField("poznámka", max_length=255, blank=True)
    version = models.PositiveIntegerField("verze", default=1)
    created_at = models.DateTimeField("vytvořeno", auto_now_add=True)
    updated_at = models.DateTimeField("upraveno", auto_now=True)

    class Meta:
        verbose_name = "směna"
        verbose_name_plural = "směny"
        ordering = ["starts_at"]
        indexes = [
            models.Index(fields=["employee", "starts_at"]),
            models.Index(fields=["workplace", "starts_at"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="shift_ends_after_starts",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee} · {self.starts_at}–{self.ends_at}"

    def clean(self) -> None:
        super().clean()
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError(
                {"ends_at": "Konec směny musí být později než začátek."}
            )

    @property
    def display_code(self) -> str:
        if self.shift_type_id:
            code = self.shift_type.code
            if self.shift_type.kind == ShiftType.Kind.STANDBY:
                return f"({code})"
            if self.shift_type.kind == ShiftType.Kind.LEAVE:
                portion = self._leave_portion()
                if portion == "am":
                    return f"{code}/"
                if portion == "pm":
                    return f"{code}\\"
            return code
        return "·"

    def _leave_portion(self) -> str:
        days = getattr(self, "_prefetched_objects_cache", {}).get("leave_plan_days")
        if days is not None:
            if days:
                return days[0].portion
            return "full"
        linked = self.leave_plan_days.all()[:1]
        if linked:
            return linked[0].portion
        return "full"

    @property
    def is_editable(self) -> bool:
        return self.status != self.Status.CANCELLED

    def planned_net_minutes(self) -> int:
        if self.status == self.Status.CANCELLED:
            return 0
        if self.shift_type_id:
            if self.shift_type.kind == ShiftType.Kind.STANDBY:
                return 0
            if self.shift_type.kind == ShiftType.Kind.LEAVE:
                return max(
                    0, int((self.ends_at - self.starts_at).total_seconds() // 60)
                )
            if self.shift_type.counts_as_work:
                return self.shift_type.net_minutes()
            return 0
        gross = int((self.ends_at - self.starts_at).total_seconds() // 60)
        return max(0, gross)


WEEKDAY_LABELS_SHORT = (
    "Po",
    "Út",
    "St",
    "Čt",
    "Pá",
    "So",
    "Ne",
)


class ScheduleTemplate(models.Model):
    """Cyklická šablona typů směn (7 nebo 14 dní)."""

    CYCLE_CHOICES = (
        (7, "7 dní (týden)"),
        (14, "14 dní (krátký/dlouhý)"),
    )

    name = models.CharField("název", max_length=120)
    is_active = models.BooleanField("aktivní", default=True, db_index=True)
    cycle_length = models.PositiveSmallIntegerField(
        "délka cyklu (dny)",
        choices=CYCLE_CHOICES,
        default=7,
    )

    class Meta:
        verbose_name = "šablona směn"
        verbose_name_plural = "šablony směn"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def type_for_index(self, day_index: int) -> ShiftType | None:
        if day_index < 0 or day_index >= self.cycle_length:
            return None
        slot = self.slots.filter(day_index=day_index).select_related("shift_type").first()
        if not slot:
            return None
        return slot.shift_type

    def type_for_date(self, day: date, anchor: date) -> ShiftType | None:
        delta = (day - anchor).days
        if self.cycle_length <= 0:
            return None
        index = delta % self.cycle_length
        if index < 0:
            index += self.cycle_length
        return self.type_for_index(index)

    def pattern_codes(self) -> str:
        slots = {
            s.day_index: s.shift_type
            for s in self.slots.select_related("shift_type").all()
        }
        parts = []
        for i in range(self.cycle_length):
            st = slots.get(i)
            parts.append(st.code if st else "·")
        return "".join(parts)

    def ensure_slots(self) -> None:
        existing = set(self.slots.values_list("day_index", flat=True))
        for i in range(self.cycle_length):
            if i not in existing:
                ScheduleTemplateSlot.objects.create(template=self, day_index=i)
        self.slots.filter(day_index__gte=self.cycle_length).delete()


class ScheduleTemplateSlot(models.Model):
    template = models.ForeignKey(
        ScheduleTemplate,
        on_delete=models.CASCADE,
        related_name="slots",
        verbose_name="šablona",
    )
    day_index = models.PositiveSmallIntegerField("den v cyklu")
    shift_type = models.ForeignKey(
        ShiftType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="typ směny",
    )

    class Meta:
        verbose_name = "den šablony"
        verbose_name_plural = "dny šablony"
        ordering = ["day_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "day_index"],
                name="uniq_schedule_template_day_index",
            ),
        ]

    def __str__(self) -> str:
        code = self.shift_type.code if self.shift_type_id else "·"
        return f"{self.template_id}[{self.day_index}]={code}"

    def label(self) -> str:
        week = self.day_index // 7 + 1
        dow = WEEKDAY_LABELS_SHORT[self.day_index % 7]
        return f"Týden {week} · {dow} (den {self.day_index + 1})"


class EmployeeScheduleAssignment(models.Model):
    """Přiřazení cyklické šablony zaměstnanci na období."""

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="schedule_assignments",
        verbose_name="zaměstnanec",
    )
    template = models.ForeignKey(
        ScheduleTemplate,
        on_delete=models.PROTECT,
        related_name="assignments",
        verbose_name="šablona",
    )
    workplace = models.ForeignKey(
        "workplaces.Workplace",
        on_delete=models.PROTECT,
        related_name="schedule_assignments",
        verbose_name="pracoviště",
    )
    valid_from = models.DateField("platnost od")
    valid_to = models.DateField("platnost do", null=True, blank=True)
    cycle_anchor_date = models.DateField(
        "kotva cyklu",
        help_text="Datum, které odpovídá 1. dni šablony (index 0). Pro fázový posun u nepřetržitého provozu.",
    )
    is_active = models.BooleanField("aktivní", default=True, db_index=True)

    class Meta:
        verbose_name = "přiřazení šablony směn"
        verbose_name_plural = "přiřazení šablon směn"
        ordering = ["-valid_from", "employee_id"]
        indexes = [
            models.Index(fields=["employee", "valid_from"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.employee} · {self.template}"

    def clean(self) -> None:
        super().clean()
        if self.valid_to and self.valid_from and self.valid_to < self.valid_from:
            raise ValidationError(
                {"valid_to": "Konec platnosti musí být stejný nebo pozdější než začátek."}
            )
        if not self.cycle_anchor_date and self.valid_from:
            self.cycle_anchor_date = self.valid_from
        if not self.employee_id or not self.valid_from:
            return
        qs = EmployeeScheduleAssignment.objects.filter(
            employee_id=self.employee_id,
            is_active=True,
        )
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        for other in qs:
            other_end = other.valid_to or date.max
            self_end = self.valid_to or date.max
            if self.valid_from <= other_end and other.valid_from <= self_end:
                raise ValidationError(
                    "Zaměstnanec má v tomto období už jiné aktivní přiřazení šablony."
                )

    def covers(self, day: date) -> bool:
        if not self.is_active:
            return False
        if day < self.valid_from:
            return False
        if self.valid_to and day > self.valid_to:
            return False
        return True

    def type_for_day(self, day: date) -> ShiftType | None:
        if not self.covers(day) or not self.template_id:
            return None
        anchor = self.cycle_anchor_date or self.valid_from
        return self.template.type_for_date(day, anchor)
