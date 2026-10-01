"""Formuláře docházky."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django import forms
from django.utils import timezone

from apps.workplaces.models import Workplace

from .models import AbsenceType


class ConfirmWorkForm(forms.Form):
    start_time = forms.TimeField(
        label="Začátek",
        widget=forms.TimeInput(
            attrs={"type": "time"},
            format="%H:%M",
        ),
        input_formats=["%H:%M", "%H:%M:%S"],
    )
    end_time = forms.TimeField(
        label="Konec",
        widget=forms.TimeInput(
            attrs={"type": "time"},
            format="%H:%M",
        ),
        input_formats=["%H:%M", "%H:%M:%S"],
    )
    break_minutes = forms.IntegerField(
        label="Neplacená pauza (min)",
        min_value=0,
        max_value=24 * 60,
        required=False,
        initial=0,
    )
    note = forms.CharField(
        label="Poznámka",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )
    expected_version = forms.IntegerField(required=False, widget=forms.HiddenInput)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("break_minutes") is None:
            cleaned["break_minutes"] = 0
        return cleaned

    def datetimes_for_day(self, day):
        """Spojí den s časy; při konci ≤ začátku posune konec na další den."""
        start_t = self.cleaned_data["start_time"]
        end_t = self.cleaned_data["end_time"]
        tz = timezone.get_current_timezone()
        starts_at = timezone.make_aware(datetime.combine(day, start_t), tz)
        end_day = day
        if end_t <= start_t:
            end_day = day + timedelta(days=1)
        ends_at = timezone.make_aware(datetime.combine(end_day, end_t), tz)
        return starts_at, ends_at


class AdHocWorkForm(forms.Form):
    workplace = forms.ModelChoiceField(
        label="Pracoviště",
        queryset=Workplace.objects.none(),
    )
    start_time = forms.TimeField(
        label="Začátek",
        widget=forms.TimeInput(
            attrs={"type": "time"},
            format="%H:%M",
        ),
        input_formats=["%H:%M", "%H:%M:%S"],
    )
    end_time = forms.TimeField(
        label="Konec",
        widget=forms.TimeInput(
            attrs={"type": "time"},
            format="%H:%M",
        ),
        input_formats=["%H:%M", "%H:%M:%S"],
    )
    break_minutes = forms.IntegerField(
        label="Neplacená pauza (min)",
        min_value=0,
        max_value=24 * 60,
        required=False,
        initial=30,
    )
    note = forms.CharField(
        label="Poznámka",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )

    def __init__(self, *args, workplace_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = workplace_queryset
        if qs is None:
            qs = Workplace.objects.filter(is_active=True).order_by("name")
        self.fields["workplace"].queryset = qs

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("break_minutes") is None:
            cleaned["break_minutes"] = 0
        return cleaned

    def datetimes_for_day(self, day):
        """Spojí den s časy; při konci ≤ začátku posune konec na další den."""
        start_t = self.cleaned_data["start_time"]
        end_t = self.cleaned_data["end_time"]
        tz = timezone.get_current_timezone()
        starts_at = timezone.make_aware(datetime.combine(day, start_t), tz)
        end_day = day
        if end_t <= start_t:
            end_day = day + timedelta(days=1)
        ends_at = timezone.make_aware(datetime.combine(end_day, end_t), tz)
        return starts_at, ends_at


class AbsenceForm(forms.Form):
    absence_type = forms.ModelChoiceField(
        label="Typ absence",
        queryset=AbsenceType.objects.none(),
        empty_label=None,
    )
    note = forms.CharField(
        label="Poznámka",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["absence_type"].queryset = AbsenceType.objects.filter(
            is_active=True
        ).order_by("sort_order", "name")


def local_dt_for_input(dt):
    """Připraví aware datetime pro datetime-local widget."""
    if dt is None:
        return None
    local = timezone.localtime(dt)
    return local.replace(second=0, microsecond=0)


def local_time_for_input(dt) -> time | None:
    """Lokální čas HH:mm pro type=time."""
    if dt is None:
        return None
    local = timezone.localtime(dt)
    return local.time().replace(second=0, microsecond=0)
