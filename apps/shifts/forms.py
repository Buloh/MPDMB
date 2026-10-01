from datetime import date

from django import forms
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.employees.models import (
    BalancingPeriod,
    Employee,
    Employment,
    WorkTimePreset,
    WorkTimeProfile,
)
from apps.workplaces.models import Workplace

from .models import (
    EmployeeScheduleAssignment,
    ScheduleTemplate,
    ScheduleTemplateSlot,
    Shift,
    ShiftType,
)


class ShiftTypeForm(forms.ModelForm):
    class Meta:
        model = ShiftType
        fields = (
            "code",
            "name",
            "kind",
            "start_time",
            "end_time",
            "break_minutes",
            "counts_as_work",
            "applies_on_holiday",
            "is_active",
            "sort_order",
        )
        labels = {
            "code": "Symbol",
            "name": "Název",
            "kind": "Druh",
            "start_time": "Začátek",
            "end_time": "Konec",
            "break_minutes": "Neplacená pauza (min)",
            "counts_as_work": "Započítat do plánu",
            "applies_on_holiday": "Povoleno ve svátek",
            "is_active": "Aktivní",
            "sort_order": "Pořadí",
        }
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "end_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }
        help_texts = {
            "code": "Krátký symbol v měsíční matici, např. R.",
            "kind": (
                "Pohotovost se v matici zobrazí v závorkách a nezapočítá "
                "do sloupce Plánováno (§ 140)."
            ),
            "end_time": "Pokud je konec dříve nebo roven začátku, směna jde přes půlnoc.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start_time"].input_formats = ["%H:%M", "%H:%M:%S"]
        self.fields["end_time"].input_formats = ["%H:%M", "%H:%M:%S"]

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not code:
            raise forms.ValidationError("Zadejte symbol.")
        return code


class ShiftForm(forms.ModelForm):
    """Úprava již přiřazené směny (zaměstnanec + den)."""

    starts_at = forms.CharField(
        label="Začátek",
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )
    ends_at = forms.CharField(
        label="Konec",
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )

    class Meta:
        model = Shift
        fields = (
            "employee",
            "workplace",
            "shift_type",
            "starts_at",
            "ends_at",
            "note",
        )
        labels = {
            "employee": "Zaměstnanec",
            "workplace": "Pracoviště",
            "shift_type": "Typ směny",
            "note": "Poznámka",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(
            is_active=True
        ).order_by("last_name", "first_name")
        self.fields["workplace"].queryset = Workplace.objects.filter(
            is_active=True
        ).order_by("name")
        self.fields["shift_type"].queryset = ShiftType.objects.filter(
            is_active=True
        ).order_by("sort_order", "code")
        self.fields["shift_type"].required = True
        if self.instance and self.instance.pk:
            tz = timezone.get_current_timezone()
            for name in ("starts_at", "ends_at"):
                value = getattr(self.instance, name)
                if value:
                    local = timezone.localtime(value, tz)
                    self.initial[name] = local.strftime("%Y-%m-%dT%H:%M")

    def _parse_local(self, raw: str):
        raw = (raw or "").strip()
        if not raw:
            return None
        if "T" not in raw and " " in raw:
            raw = raw.replace(" ", "T")
        parsed = parse_datetime(raw)
        if parsed is None:
            raise forms.ValidationError("Zadejte platné datum a čas.")
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(
                parsed, timezone.get_current_timezone()
            )
        return parsed

    def clean_starts_at(self):
        return self._parse_local(self.cleaned_data["starts_at"])

    def clean_ends_at(self):
        return self._parse_local(self.cleaned_data["ends_at"])

    def clean(self):
        cleaned = super().clean()
        shift_type = cleaned.get("shift_type")
        starts = cleaned.get("starts_at")
        if shift_type and starts:
            day = timezone.localtime(starts).date()
            cleaned["starts_at"], cleaned["ends_at"] = shift_type.bounds_for_date(day)
        starts = cleaned.get("starts_at")
        ends = cleaned.get("ends_at")
        if starts and ends and ends <= starts:
            self.add_error("ends_at", "Konec směny musí být později než začátek.")
        return cleaned


class ShiftCellForm(forms.Form):
    employee = forms.ModelChoiceField(
        label="Zaměstnanec",
        queryset=Employee.objects.filter(is_active=True),
    )
    workplace = forms.ModelChoiceField(
        label="Pracoviště",
        queryset=Workplace.objects.filter(is_active=True),
    )
    day = forms.DateField(label="Den", widget=forms.DateInput(attrs={"type": "date"}))
    shift_type = forms.ModelChoiceField(
        label="Typ směny",
        queryset=ShiftType.objects.filter(is_active=True),
    )
    publish = forms.BooleanField(
        label="Hned publikovat",
        required=False,
        initial=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(
            is_active=True
        ).order_by("last_name", "first_name")
        self.fields["workplace"].queryset = Workplace.objects.filter(
            is_active=True
        ).order_by("name")
        self.fields["shift_type"].queryset = ShiftType.objects.filter(
            is_active=True
        ).order_by("sort_order", "code")


class ScheduleTemplateForm(forms.ModelForm):
    class Meta:
        model = ScheduleTemplate
        fields = ("name", "is_active", "cycle_length")
        labels = {
            "name": "Název",
            "is_active": "Aktivní",
            "cycle_length": "Délka cyklu",
        }

    def save_slots(self, template: ScheduleTemplate, post_data) -> None:
        template.ensure_slots()
        type_ids = {
            str(t.pk): t
            for t in ShiftType.objects.filter(is_active=True)
        }
        for i in range(template.cycle_length):
            raw = (post_data.get(f"slot_{i}") or "").strip()
            st = type_ids.get(raw) if raw else None
            ScheduleTemplateSlot.objects.filter(
                template=template, day_index=i
            ).update(shift_type=st)


class EmployeeScheduleAssignmentForm(forms.ModelForm):
    class Meta:
        model = EmployeeScheduleAssignment
        fields = (
            "employee",
            "template",
            "workplace",
            "valid_from",
            "valid_to",
            "cycle_anchor_date",
            "is_active",
        )
        labels = {
            "employee": "Zaměstnanec",
            "template": "Šablona",
            "workplace": "Pracoviště",
            "valid_from": "Platnost od",
            "valid_to": "Platnost do",
            "cycle_anchor_date": "Kotva cyklu",
            "is_active": "Aktivní",
        }
        widgets = {
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "valid_to": forms.DateInput(attrs={"type": "date"}),
            "cycle_anchor_date": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "cycle_anchor_date": "1. den šablony. Posunem kotvy fázujete nepřetržitý provoz.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(
            is_active=True
        ).order_by("last_name", "first_name")
        self.fields["template"].queryset = ScheduleTemplate.objects.filter(
            is_active=True
        ).order_by("name")
        self.fields["workplace"].queryset = Workplace.objects.filter(
            is_active=True
        ).order_by("name")
        self.fields["valid_to"].required = False

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("valid_from") and not cleaned.get("cycle_anchor_date"):
            cleaned["cycle_anchor_date"] = cleaned["valid_from"]
        return cleaned


class WorkTimeProfileForm(forms.ModelForm):
    preset = forms.ModelChoiceField(
        label="Předvolba úvazku",
        queryset=WorkTimePreset.objects.none(),
        required=False,
        help_text=(
            "Fond se počítá ze sjednané týdenní doby; předvolba jen vyplní "
            "stanovenou i sjednanou hodnotu (lze pak upravit)."
        ),
    )

    class Meta:
        model = WorkTimeProfile
        fields = (
            "employment",
            "valid_from",
            "valid_to",
            "statutory_weekly_minutes",
            "agreed_weekly_minutes",
            "regime",
            "distribution",
            "is_active",
        )
        labels = {
            "employment": "Pracovní vztah",
            "valid_from": "Platnost od",
            "valid_to": "Platnost do",
            "statutory_weekly_minutes": "Stanovená týdenní doba (min)",
            "agreed_weekly_minutes": "Sjednaná týdenní doba (min)",
            "regime": "Režim",
            "distribution": "Rozvržení",
            "is_active": "Aktivní",
        }
        widgets = {
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "valid_to": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "statutory_weekly_minutes": "40 h = 2400, 38,75 h = 2325, 37,5 h = 2250.",
            "agreed_weekly_minutes": (
                "Skutečný úvazek. Denní fond = sjednaná ÷ dny režimu."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employment"].queryset = Employment.objects.filter(
            is_active=True
        ).select_related("employee").order_by(
            "employee__last_name", "-started_on"
        )
        self.fields["valid_to"].required = False
        self.fields["preset"].queryset = WorkTimePreset.objects.filter(
            is_active=True
        ).order_by("sort_order", "name")
        # Zobrazit předvolbu před poli minut
        self.order_fields(
            [
                "employment",
                "valid_from",
                "valid_to",
                "preset",
                "statutory_weekly_minutes",
                "agreed_weekly_minutes",
                "regime",
                "distribution",
                "is_active",
            ]
        )
        self.derived_daily_label = self._derived_daily_label(
            self.initial.get("agreed_weekly_minutes")
            or getattr(self.instance, "agreed_weekly_minutes", None)
            or 40 * 60,
            self.initial.get("regime")
            or getattr(self.instance, "regime", None)
            or WorkTimeProfile.Regime.SINGLE,
        )

    @staticmethod
    def days_per_week_for_regime(regime: str) -> int:
        if regime == WorkTimeProfile.Regime.CONTINUOUS:
            return 7
        return 5

    @classmethod
    def _derived_daily_label(cls, agreed_weekly: int, regime: str) -> str:
        days = cls.days_per_week_for_regime(regime)
        daily = max(1, int(agreed_weekly) // days)
        wh = agreed_weekly // 60
        wm = agreed_weekly % 60
        weekly = f"{wh}:{wm:02d}" if wm else f"{wh}"
        dh = daily // 60
        dm = daily % 60
        daily_s = f"{dh}:{dm:02d}" if dm else f"{dh}"
        return f"{weekly} h/týden → {daily_s} h/den (÷{days})"

    def clean(self):
        cleaned = super().clean()
        preset = cleaned.get("preset")
        regime = cleaned.get("regime") or WorkTimeProfile.Regime.SINGLE
        if preset:
            cleaned["statutory_weekly_minutes"] = preset.weekly_minutes
            cleaned["agreed_weekly_minutes"] = preset.weekly_minutes
        agreed = cleaned.get("agreed_weekly_minutes")
        if agreed:
            self.derived_daily_label = self._derived_daily_label(agreed, regime)

        employment = cleaned.get("employment")
        valid_from = cleaned.get("valid_from")
        valid_to = cleaned.get("valid_to")
        if employment and valid_from and cleaned.get("is_active", True):
            others = WorkTimeProfile.objects.filter(
                employment=employment,
                is_active=True,
            )
            if self.instance.pk:
                others = others.exclude(pk=self.instance.pk)
            new_end = valid_to or date.max
            for other in others:
                other_end = other.valid_to or date.max
                if valid_from <= other_end and other.valid_from <= new_end:
                    self.add_error(
                        None,
                        (
                            "Překrývá se s jiným aktivním profilem "
                            f"od {other.valid_from:%d.%m.%Y}"
                            + (
                                f" do {other.valid_to:%d.%m.%Y}"
                                if other.valid_to
                                else " (bez konce)"
                            )
                            + ". Nejdřív ukončete starý profil."
                        ),
                    )
                    break
        return cleaned


class WorkTimePresetForm(forms.ModelForm):
    class Meta:
        model = WorkTimePreset
        fields = ("name", "weekly_minutes", "sort_order", "is_active")
        labels = {
            "name": "Název",
            "weekly_minutes": "Týdenní doba (min)",
            "sort_order": "Pořadí",
            "is_active": "Aktivní",
        }
        help_texts = {
            "weekly_minutes": "40 h = 2400, 38,75 h = 2325, 37,5 h = 2250, 30 h = 1800.",
            "name": "Např. „40 hodin“ nebo „Kratší úvazek 30 h“.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_active"].required = False


class BalancingPeriodForm(forms.ModelForm):
    auto_target = forms.BooleanField(
        label="Dopočítat cíl dynamicky z úvazku (po dnech)",
        required=False,
        initial=True,
    )

    class Meta:
        model = BalancingPeriod
        fields = (
            "profile",
            "starts_on",
            "ends_on",
            "kind",
            "target_minutes",
            "note",
        )
        labels = {
            "profile": "Profil pracovní doby",
            "starts_on": "Začátek",
            "ends_on": "Konec",
            "kind": "Druh",
            "target_minutes": "Cílový fond (min)",
            "note": "Poznámka",
        }
        widgets = {
            "starts_on": forms.DateInput(attrs={"type": "date"}),
            "ends_on": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["profile"].queryset = WorkTimeProfile.objects.filter(
            is_active=True
        ).select_related("employment__employee").order_by("-valid_from")
        self.fields["target_minutes"].required = False

    def clean(self):
        from apps.shifts.fund import dynamic_balancing_target_minutes

        cleaned = super().clean()
        profile = cleaned.get("profile")
        starts = cleaned.get("starts_on")
        ends = cleaned.get("ends_on")
        auto = cleaned.get("auto_target")
        target = cleaned.get("target_minutes")
        if (auto or not target) and profile and starts and ends:
            draft = BalancingPeriod(
                profile=profile,
                starts_on=starts,
                ends_on=ends,
                kind=cleaned.get("kind") or BalancingPeriod.Kind.SCHEDULE,
                target_minutes=1,
            )
            cleaned["target_minutes"] = dynamic_balancing_target_minutes(draft)
        if not cleaned.get("target_minutes"):
            self.add_error(
                "target_minutes",
                "Zadejte cílový fond, nebo zapněte dopočet.",
            )
        return cleaned


class WorkTimeBulkForm(forms.Form):
    employees = forms.ModelMultipleChoiceField(
        label="Zaměstnanci",
        queryset=Employee.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )
    valid_from = forms.DateField(
        label="Platnost od",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    valid_to = forms.DateField(
        label="Platnost do",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    preset = forms.ModelChoiceField(
        label="Předvolba úvazku",
        queryset=WorkTimePreset.objects.none(),
        required=False,
        help_text=(
            "Fond se počítá ze sjednané týdenní doby; předvolba jen vyplní "
            "stanovenou i sjednanou hodnotu (lze pak upravit)."
        ),
    )
    statutory_weekly_minutes = forms.IntegerField(
        label="Stanovená týdenní doba (min)",
        min_value=1,
        initial=40 * 60,
        help_text="40 h = 2400, 38,75 h = 2325, 37,5 h = 2250.",
    )
    agreed_weekly_minutes = forms.IntegerField(
        label="Sjednaná týdenní doba (min)",
        min_value=1,
        initial=40 * 60,
        help_text="Skutečný úvazek. Denní fond = sjednaná ÷ dny režimu.",
    )
    regime = forms.ChoiceField(
        label="Režim",
        choices=WorkTimeProfile.Regime.choices,
        initial=WorkTimeProfile.Regime.SINGLE,
    )
    distribution = forms.ChoiceField(
        label="Rozvržení",
        choices=WorkTimeProfile.Distribution.choices,
        initial=WorkTimeProfile.Distribution.EVEN,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employees"].queryset = Employee.objects.filter(
            is_active=True
        ).order_by("last_name", "first_name")
        self.fields["preset"].queryset = WorkTimePreset.objects.filter(
            is_active=True
        ).order_by("sort_order", "name")
        if not self.is_bound:
            self.fields["valid_from"].initial = timezone.localdate()
        agreed = (
            self.data.get("agreed_weekly_minutes")
            if self.is_bound
            else self.fields["agreed_weekly_minutes"].initial
        )
        regime = (
            self.data.get("regime")
            if self.is_bound
            else self.fields["regime"].initial
        )
        try:
            agreed_i = int(agreed) if agreed else 40 * 60
        except (TypeError, ValueError):
            agreed_i = 40 * 60
        self.derived_daily_label = WorkTimeProfileForm._derived_daily_label(
            agreed_i, regime or WorkTimeProfile.Regime.SINGLE
        )

    def clean(self):
        cleaned = super().clean()
        preset = cleaned.get("preset")
        regime = cleaned.get("regime") or WorkTimeProfile.Regime.SINGLE
        if preset:
            cleaned["statutory_weekly_minutes"] = preset.weekly_minutes
            cleaned["agreed_weekly_minutes"] = preset.weekly_minutes
        agreed = cleaned.get("agreed_weekly_minutes")
        if agreed:
            self.derived_daily_label = WorkTimeProfileForm._derived_daily_label(
                agreed, regime
            )
        return cleaned


class BalancingPeriodBulkForm(forms.Form):
    employees = forms.ModelMultipleChoiceField(
        label="Zaměstnanci",
        queryset=Employee.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Ponechte prázdné a zaškrtněte „všichni s aktivním profilem“.",
    )
    all_with_active_profile = forms.BooleanField(
        label="Všichni s aktivním profilem",
        required=False,
        initial=False,
    )
    starts_on = forms.DateField(
        label="Začátek",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    ends_on = forms.DateField(
        label="Konec",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    kind = forms.ChoiceField(
        label="Druh",
        choices=BalancingPeriod.Kind.choices,
        initial=BalancingPeriod.Kind.SCHEDULE,
    )
    auto_target = forms.BooleanField(
        label="Dopočítat cíl ze sjednané týdenní doby",
        required=False,
        initial=True,
    )
    target_minutes = forms.IntegerField(
        label="Cílový fond (min)",
        required=False,
        min_value=1,
    )
    note = forms.CharField(label="Poznámka", required=False, max_length=255)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employees"].queryset = Employee.objects.filter(
            is_active=True,
            employments__work_time_profiles__is_active=True,
        ).distinct().order_by("last_name", "first_name")

    def clean(self):
        cleaned = super().clean()
        employees = cleaned.get("employees")
        all_profiles = cleaned.get("all_with_active_profile")
        if not all_profiles and not employees:
            raise forms.ValidationError(
                "Vyberte zaměstnance, nebo zaškrtněte „všichni s aktivním profilem“."
            )
        starts = cleaned.get("starts_on")
        ends = cleaned.get("ends_on")
        if starts and ends and ends < starts:
            self.add_error(
                "ends_on",
                "Konec období musí být stejný nebo pozdější než začátek.",
            )
        auto = cleaned.get("auto_target")
        target = cleaned.get("target_minutes")
        if not auto and not target:
            self.add_error(
                "target_minutes",
                "Zadejte cílový fond, nebo zapněte dopočet.",
            )
        return cleaned


class GenerateShiftsForm(forms.Form):
    RANGE_MONTH = "month"
    RANGE_YEAR = "year"
    RANGE_CUSTOM = "custom"
    RANGE_CHOICES = (
        (RANGE_MONTH, "Měsíc"),
        (RANGE_YEAR, "Celý rok"),
        (RANGE_CUSTOM, "Od–do"),
    )

    range_mode = forms.ChoiceField(
        label="Rozsah",
        choices=RANGE_CHOICES,
        initial=RANGE_MONTH,
        widget=forms.RadioSelect,
    )
    year = forms.IntegerField(label="Rok", min_value=2020, max_value=2100)
    month = forms.IntegerField(label="Měsíc", min_value=1, max_value=12)
    date_from = forms.DateField(
        label="Od",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    date_to = forms.DateField(
        label="Do",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    template = forms.ModelChoiceField(
        label="Šablona",
        queryset=ScheduleTemplate.objects.filter(is_active=True),
        help_text="Šablona pro tento běh generování (ne trvalé přiřazení).",
    )
    workplace = forms.ModelChoiceField(
        label="Pracoviště",
        queryset=Workplace.objects.filter(is_active=True),
    )
    cycle_anchor_date = forms.DateField(
        label="Kotva cyklu",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text=(
            "1. den šablony (u Po–Pá šablony obvykle pondělí). "
            "Výchozí = pondělí týdne začátku intervalu."
        ),
    )
    employees = forms.ModelMultipleChoiceField(
        label="Zaměstnanci",
        queryset=Employee.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )

    def __init__(self, *args, employee_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = employee_queryset
        if qs is None:
            qs = Employee.objects.filter(is_active=True).order_by(
                "last_name", "first_name"
            )
        self.fields["employees"].queryset = qs
        self.fields["template"].queryset = ScheduleTemplate.objects.filter(
            is_active=True
        ).order_by("name")
        self.fields["workplace"].queryset = Workplace.objects.filter(
            is_active=True
        ).order_by("name")

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get("range_mode")
        year = cleaned.get("year")
        month = cleaned.get("month")
        if mode == self.RANGE_MONTH and year and month:
            from calendar import monthrange

            last = monthrange(year, month)[1]
            cleaned["date_from"] = date(year, month, 1)
            cleaned["date_to"] = date(year, month, last)
        elif mode == self.RANGE_YEAR and year:
            cleaned["date_from"] = date(year, 1, 1)
            cleaned["date_to"] = date(year, 12, 31)
        else:
            if not cleaned.get("date_from") or not cleaned.get("date_to"):
                self.add_error("date_from", "Zadejte interval od–do.")
            elif cleaned["date_to"] < cleaned["date_from"]:
                self.add_error(
                    "date_to", "Konec musí být stejný nebo pozdější než začátek."
                )
        if cleaned.get("date_from") and not cleaned.get("cycle_anchor_date"):
            from apps.shifts.services import monday_of_week

            cleaned["cycle_anchor_date"] = monday_of_week(cleaned["date_from"])

        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        employees = cleaned.get("employees")
        if date_from and date_to and employees:
            from apps.shifts.services import (
                filter_employees_with_employment_in_range,
            )

            allowed = set(
                filter_employees_with_employment_in_range(
                    Employee.objects.filter(
                        pk__in=[e.pk for e in employees]
                    ),
                    date_from,
                    date_to,
                ).values_list("pk", flat=True)
            )
            bad = [e for e in employees if e.pk not in allowed]
            if bad:
                names = ", ".join(f"{e.last_name} {e.first_name}" for e in bad)
                self.add_error(
                    "employees",
                    (
                        "Tito zaměstnanci nemají aktivní pracovní vztah "
                        f"v zvoleném období: {names}."
                    ),
                )
        return cleaned


class ShiftCellModalForm(forms.Form):
    shift_type = forms.ModelChoiceField(
        label="Typ směny",
        queryset=ShiftType.objects.filter(is_active=True),
    )
    publish = forms.BooleanField(
        label="Hned publikovat",
        required=False,
        initial=True,
    )

    def __init__(self, *args, type_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if type_queryset is not None:
            self.fields["shift_type"].queryset = type_queryset
