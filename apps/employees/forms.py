from datetime import date, datetime

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from apps.workplaces.models import EmployeeWorkplace, Workplace

from .models import (
    Employee,
    EmployeeQualification,
    Employment,
    QualificationType,
    WorkTimePreset,
    WorkTimeProfile,
)


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = (
            "first_name",
            "last_name",
            "internal_number",
            "job_title",
            "phone",
            "email",
            "work_contact",
            "notes",
            "user",
            "is_active",
        )
        labels = {
            "first_name": "Jméno",
            "last_name": "Příjmení",
            "internal_number": "Interní číslo",
            "job_title": "Funkce",
            "phone": "Telefon",
            "email": "E-mail",
            "work_contact": "Další pracovní kontakt",
            "notes": "Poznámka",
            "user": "Přihlašovací účet",
            "is_active": "Aktivní",
        }
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].required = False
        self.fields["user"].queryset = self.fields["user"].queryset.order_by(
            "username"
        )


class EmploymentForm(forms.ModelForm):
    class Meta:
        model = Employment
        fields = (
            "relation_type",
            "started_on",
            "ended_on",
            "payroll_number",
            "pay_regime",
            "job_title",
            "is_active",
        )
        labels = {
            "relation_type": "Druh vztahu",
            "started_on": "Den nástupu",
            "ended_on": "Den ukončení",
            "payroll_number": "Mzdové číslo",
            "pay_regime": "Režim odměňování",
            "job_title": "Funkce ve vztahu",
            "is_active": "Aktivní vztah",
        }
        widgets = {
            "started_on": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "ended_on": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
        }
        help_texts = {
            "relation_type": (
                "Pro DPP a DPČ zatím nelze vytvářet finální mzdový export "
                "stejnými pravidly jako u pracovního poměru."
            ),
            "payroll_number": "Ukládejte včetně počátečních nul.",
            "ended_on": "Nechte prázdné, pokud vztah probíhá.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("started_on", "ended_on"):
            self.fields[name].input_formats = ["%Y-%m-%d", "%d.%m.%Y"]
        self.fields["ended_on"].required = False
        self.fields["job_title"].required = False

    def clean(self):
        cleaned = super().clean()
        started = cleaned.get("started_on")
        ended = cleaned.get("ended_on")
        if started and ended and ended < started:
            self.add_error(
                "ended_on",
                "Den ukončení nesmí být dříve než den nástupu.",
            )
        return cleaned


class EmployeeQualificationForm(forms.ModelForm):
    class Meta:
        model = EmployeeQualification
        fields = (
            "qualification_type",
            "number",
            "categories",
            "valid_from",
            "valid_until",
            "issued_by",
            "notes",
            "is_active",
        )
        labels = {
            "qualification_type": "Typ",
            "number": "Číslo",
            "categories": "Skupiny / rozsah",
            "valid_from": "Platnost od",
            "valid_until": "Platnost do",
            "issued_by": "Vydal",
            "notes": "Poznámka",
            "is_active": "Aktivní",
        }
        widgets = {
            "valid_from": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "valid_until": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["qualification_type"].queryset = (
            QualificationType.objects.filter(is_active=True).order_by(
                "sort_order", "name"
            )
        )
        self.fields["qualification_type"].required = False
        for name in ("valid_from", "valid_until"):
            self.fields[name].input_formats = ["%Y-%m-%d", "%d.%m.%Y"]
            self.fields[name].required = False

    def has_changed(self):
        prefix = self.add_prefix("qualification_type")
        raw_type = ""
        if self.data is not None:
            raw_type = (self.data.get(prefix) or "").strip()
        if not raw_type and not getattr(self.instance, "pk", None):
            return False
        return super().has_changed()

    def clean(self):
        cleaned = super().clean()
        qtype = cleaned.get("qualification_type")
        if not qtype:
            return cleaned
        number = (cleaned.get("number") or "").strip()
        categories = (cleaned.get("categories") or "").strip()
        cleaned["number"] = number
        cleaned["categories"] = categories
        if qtype.requires_number and not number:
            self.add_error("number", "Tento typ vyžaduje číslo.")
        if qtype.requires_categories and not categories:
            self.add_error("categories", "Tento typ vyžaduje skupiny.")
        valid_from = cleaned.get("valid_from")
        valid_until = cleaned.get("valid_until")
        if valid_from and valid_until and valid_until < valid_from:
            self.add_error(
                "valid_until",
                "Platnost do nesmí být dříve než platnost od.",
            )
        return cleaned


class BaseEmployeeQualificationFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()


EmployeeQualificationFormSet = inlineformset_factory(
    Employee,
    EmployeeQualification,
    form=EmployeeQualificationForm,
    formset=BaseEmployeeQualificationFormSet,
    extra=1,
    can_delete=True,
)


class WorkTimePresetSelect(forms.Select):
    """Select s data-minutes na option pro JS vyplnění polí."""

    def __init__(self, *args, minutes_by_pk=None, **kwargs):
        self.minutes_by_pk = minutes_by_pk or {}
        super().__init__(*args, **kwargs)

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )
        pk = getattr(value, "value", value)
        if pk not in (None, ""):
            minutes = self.minutes_by_pk.get(int(pk))
            if minutes is not None:
                option["attrs"]["data-minutes"] = str(minutes)
        return option


class EmployeeWorkTimeForm(forms.Form):
    """Úvazek u pracovního vztahu (bez samostatné správy profilů na Fondu)."""

    preset = forms.ModelChoiceField(
        label="Předvolba úvazku",
        queryset=WorkTimePreset.objects.none(),
        required=False,
        help_text=(
            "Fond se počítá ze sjednané týdenní doby; předvolba jen vyplní "
            "stanovenou i sjednanou hodnotu (po uložení zůstane vybraná, "
            "pokud minuty stále sedí)."
        ),
    )
    valid_from = forms.DateField(
        label="Úvazek platí od",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text=(
            "Při změně úvazku zvolte nové datum od — starý profil se ukončí "
            "dnem předtím."
        ),
    )
    statutory_weekly_minutes = forms.IntegerField(
        label="Stanovená týdenní doba (min)",
        min_value=1,
        initial=40 * 60,
        help_text="Hodiny se zobrazí pod polem (např. 2325 = 38,75 h).",
    )
    agreed_weekly_minutes = forms.IntegerField(
        label="Sjednaná týdenní doba (min)",
        min_value=1,
        initial=40 * 60,
        help_text="Denní fond = sjednaná ÷ dny režimu (běžně ÷5).",
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

    def __init__(self, *args, profile: WorkTimeProfile | None = None, **kwargs):
        self.profile = profile
        super().__init__(*args, **kwargs)
        presets = list(
            WorkTimePreset.objects.filter(is_active=True).order_by(
                "sort_order", "name"
            )
        )
        minutes_by_pk = {p.pk: p.weekly_minutes for p in presets}
        self.fields["preset"].widget = WorkTimePresetSelect(
            minutes_by_pk=minutes_by_pk
        )
        self.fields["preset"].queryset = WorkTimePreset.objects.filter(
            pk__in=[p.pk for p in presets]
        ).order_by("sort_order", "name")
        self.fields["valid_from"].input_formats = ["%Y-%m-%d", "%d.%m.%Y"]
        if profile and not self.is_bound:
            self.fields["valid_from"].initial = profile.valid_from
            self.fields["statutory_weekly_minutes"].initial = (
                profile.statutory_weekly_minutes
            )
            self.fields["agreed_weekly_minutes"].initial = (
                profile.agreed_weekly_minutes
            )
            self.fields["regime"].initial = profile.regime
            self.fields["distribution"].initial = profile.distribution
        elif not self.is_bound and not self.fields["valid_from"].initial:
            self.fields["valid_from"].initial = date.today()

        if not self.is_bound:
            statutory = self.fields["statutory_weekly_minutes"].initial
            agreed = self.fields["agreed_weekly_minutes"].initial
            if statutory is not None and statutory == agreed:
                match = next(
                    (p for p in presets if p.weekly_minutes == int(agreed)),
                    None,
                )
                if match:
                    self.fields["preset"].initial = match.pk

        agreed = None
        if self.is_bound:
            agreed = self.data.get(self.add_prefix("agreed_weekly_minutes"))
        if agreed is None:
            agreed = self.fields["agreed_weekly_minutes"].initial
        regime = (
            self.data.get(self.add_prefix("regime"))
            if self.is_bound
            else self.fields["regime"].initial
        )
        try:
            agreed_i = int(agreed) if agreed else 40 * 60
        except (TypeError, ValueError):
            agreed_i = 40 * 60
        days = 7 if regime == WorkTimeProfile.Regime.CONTINUOUS else 5
        daily = max(1, agreed_i // days)
        wh, wm = agreed_i // 60, agreed_i % 60
        weekly = f"{wh}:{wm:02d}" if wm else f"{wh}"
        dh, dm = daily // 60, daily % 60
        daily_s = f"{dh}:{dm:02d}" if dm else f"{dh}"
        self.derived_daily_label = f"{weekly} h/týden → {daily_s} h/den (÷{days})"

    def clean(self):
        cleaned = super().clean()
        preset = cleaned.get("preset")
        if preset:
            cleaned["statutory_weekly_minutes"] = preset.weekly_minutes
            cleaned["agreed_weekly_minutes"] = preset.weekly_minutes
        return cleaned


class EmployeeWorkplaceInlineForm(forms.ModelForm):
    class Meta:
        model = EmployeeWorkplace
        fields = ("workplace", "valid_from", "valid_to")
        labels = {
            "workplace": "Pracoviště",
            "valid_from": "Platnost od",
            "valid_to": "Platnost do",
        }
        help_texts = {
            "valid_from": (
                "Nejdříve den nástupu; intervaly pracovišť se nesmí překrývat."
            ),
        }
        widgets = {
            "valid_from": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "valid_to": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["workplace"].queryset = Workplace.objects.filter(
            is_active=True
        ).order_by("name")
        self.fields["workplace"].required = False
        for name in ("valid_from", "valid_to"):
            self.fields[name].input_formats = ["%Y-%m-%d", "%d.%m.%Y"]
            self.fields[name].required = False

    def has_changed(self):
        prefix = self.add_prefix("workplace")
        raw = ""
        if self.data is not None:
            raw = (self.data.get(prefix) or "").strip()
        if not raw and not getattr(self.instance, "pk", None):
            return False
        return super().has_changed()

    def clean(self):
        cleaned = super().clean()
        workplace = cleaned.get("workplace")
        if not workplace:
            return cleaned
        valid_from = cleaned.get("valid_from")
        if not valid_from:
            self.add_error("valid_from", "Zadejte začátek platnosti.")
            return cleaned
        valid_to = cleaned.get("valid_to")
        if valid_to and valid_to < valid_from:
            self.add_error(
                "valid_to",
                "Platnost do nesmí být dříve než platnost od.",
            )
        return cleaned


def _intervals_overlap(a_from, a_to, b_from, b_to) -> bool:
    a_end = a_to or date.max
    b_end = b_to or date.max
    return a_from <= b_end and b_from <= a_end


class BaseEmployeeWorkplaceFormSet(BaseInlineFormSet):
    def _employment_started_on(self) -> date | None:
        """Den nástupu z formuláře vztahu (emp-started_on) nebo z DB."""
        raw = ""
        if self.data is not None:
            raw = (self.data.get("emp-started_on") or "").strip()
        if raw:
            for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
                try:
                    return datetime.strptime(raw, fmt).date()
                except ValueError:
                    continue
        employee = getattr(self, "instance", None)
        if employee is not None and getattr(employee, "pk", None):
            employment = employee.current_employment
            if employment is not None:
                return employment.started_on
        return None

    def clean(self):
        super().clean()
        intervals: list[tuple[date, date | None]] = []
        started_on = self._employment_started_on()
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            workplace = form.cleaned_data.get("workplace")
            valid_from = form.cleaned_data.get("valid_from")
            if not workplace or not valid_from:
                continue
            valid_to = form.cleaned_data.get("valid_to")
            if started_on and valid_from < started_on:
                form.add_error(
                    "valid_from",
                    "Platnost pracoviště nesmí začínat dříve než den nástupu "
                    f"({started_on:%d.%m.%Y}).",
                )
                continue
            for other_from, other_to in intervals:
                if _intervals_overlap(valid_from, valid_to, other_from, other_to):
                    raise forms.ValidationError(
                        "Platnosti pracovišť se nesmí překrývat — "
                        "v jeden den smí být jen jedno pracoviště."
                    )
            intervals.append((valid_from, valid_to))


EmployeeWorkplaceFormSet = inlineformset_factory(
    Employee,
    EmployeeWorkplace,
    form=EmployeeWorkplaceInlineForm,
    formset=BaseEmployeeWorkplaceFormSet,
    extra=1,
    can_delete=True,
)
