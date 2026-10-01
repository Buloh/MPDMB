from django import forms

from .models import EmployeeLeaveSettings, LeavePlanDay


class LeavePlanForm(forms.Form):
    starts_on = forms.DateField(
        label="Od",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d", "%d.%m.%Y"],
    )
    ends_on = forms.DateField(
        label="Do",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d", "%d.%m.%Y"],
    )
    portion = forms.ChoiceField(
        label="Část dne",
        choices=LeavePlanDay.Portion.choices,
        initial=LeavePlanDay.Portion.FULL,
        required=True,
        help_text="Půlden (dopoledne/odpoledne) jen u jednoho dne.",
    )
    note = forms.CharField(
        label="Poznámka",
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )
    approve_now = forms.BooleanField(
        label="Ihned schválit a propsat do dlouhodobého plánu",
        required=False,
        initial=True,
    )

    def __init__(self, *args, allow_half_day: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.allow_half_day = allow_half_day
        if not allow_half_day:
            self.fields["portion"].choices = [
                (LeavePlanDay.Portion.FULL, "Celý den"),
            ]
            self.fields["portion"].initial = LeavePlanDay.Portion.FULL
            self.fields["portion"].widget = forms.HiddenInput()

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("starts_on")
        end = cleaned.get("ends_on")
        if start and not end:
            cleaned["ends_on"] = start
            end = start
        portion = cleaned.get("portion") or LeavePlanDay.Portion.FULL
        if start and end and end < start:
            self.add_error("ends_on", "Konec musí být později než začátek.")
        if portion != LeavePlanDay.Portion.FULL:
            if not self.allow_half_day:
                self.add_error(
                    "portion",
                    "Půldenní dovolená není povolena.",
                )
            elif start and end and start != end:
                self.add_error(
                    "portion",
                    "Půldenní dovolená je možná jen u jednodenního bloku.",
                )
        return cleaned


class EmployeeLeaveSettingsForm(forms.ModelForm):
    """Individuální nastavení dovolené na kartě zaměstnance."""

    HALF_DAY_CHOICES = (
        ("", "Podle globálních pravidel"),
        ("1", "Ano"),
        ("0", "Ne"),
    )

    allow_half_day_choice = forms.ChoiceField(
        label="Povolit půldenní dovolenou",
        choices=HALF_DAY_CHOICES,
        required=False,
    )

    class Meta:
        model = EmployeeLeaveSettings
        fields = ("extra_weeks",)
        labels = {
            "extra_weeks": "Navíc týdnů dovolené",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["extra_weeks"].required = False
        self.fields["extra_weeks"].initial = 0
        current = None
        if self.instance and self.instance.pk:
            current = self.instance.allow_half_day
        if current is True:
            self.initial["allow_half_day_choice"] = "1"
        elif current is False:
            self.initial["allow_half_day_choice"] = "0"
        else:
            self.initial["allow_half_day_choice"] = ""

    def clean_extra_weeks(self):
        value = self.cleaned_data.get("extra_weeks")
        if value is None or value == "":
            return 0
        return value

    def clean_allow_half_day_choice(self):
        raw = self.cleaned_data.get("allow_half_day_choice")
        if raw == "1":
            return True
        if raw == "0":
            return False
        return None

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.allow_half_day = self.cleaned_data.get("allow_half_day_choice")
        if commit:
            obj.save()
        return obj
