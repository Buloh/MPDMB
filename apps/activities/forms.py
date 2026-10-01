"""Formuláře činností."""

from __future__ import annotations

import json

from django import forms
from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone

from apps.employees.models import Employee
from apps.shifts.models import Shift
from apps.technika.models import Vehicle
from apps.workplaces.models import Workplace

from .models import ActivityItem, ActivityLocation, ActivityType, next_location_color

VEHICLE_EMPTY_NO_FLEET = "— nejdříve založte vozidlo v Technice —"
VEHICLE_EMPTY_OPTIONAL = "— bez vozidla —"


def _vehicle_empty_label() -> str:
    if Vehicle.objects.filter(is_active=True).exists():
        return VEHICLE_EMPTY_OPTIONAL
    return VEHICLE_EMPTY_NO_FLEET


def _locations_for_choice():
    return (
        ActivityLocation.objects.filter(is_active=True)
        .select_related("parent")
        .annotate(
            _root=Case(
                When(parent__isnull=True, then="id"),
                default="parent_id",
                output_field=IntegerField(),
            ),
            _is_sub=Case(
                When(parent__isnull=False, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            ),
        )
        .order_by("_root", "_is_sub", "sort_order", "code")
    )


class ActivityLocationForm(forms.ModelForm):
    class Meta:
        model = ActivityLocation
        fields = (
            "code",
            "name",
            "description",
            "parent",
            "workplace",
            "color",
            "geojson",
            "is_active",
            "sort_order",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "geojson": forms.HiddenInput(),
            "color": forms.TextInput(attrs={"type": "color"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["workplace"].queryset = Workplace.objects.filter(
            is_active=True
        ).order_by("name")
        self.fields["workplace"].required = False
        self.fields["parent"].required = False
        self.fields["parent"].empty_label = "— hlavní lokace —"
        parents = ActivityLocation.objects.filter(
            is_active=True, parent__isnull=True
        ).order_by("sort_order", "code")
        if self.instance and self.instance.pk:
            parents = parents.exclude(pk=self.instance.pk)
            child_ids = list(
                self.instance.children.values_list("pk", flat=True)
            )
            if child_ids:
                parents = parents.exclude(pk__in=child_ids)
        self.fields["parent"].queryset = parents
        self.fields["parent"].label_from_instance = (
            lambda obj: f"{obj.code} – {obj.name}"
        )
        if not self.is_bound and not (self.instance and self.instance.pk):
            self.fields["color"].initial = next_location_color()

    def clean_color(self):
        raw = (self.cleaned_data.get("color") or "").strip()
        if not raw:
            raise forms.ValidationError("Zadejte barvu polygonu.")
        if not raw.startswith("#"):
            raw = f"#{raw}"
        raw = raw.upper()
        if len(raw) != 7:
            raise forms.ValidationError("Zadejte barvu ve formátu #RRGGBB.")
        return raw

    def clean_geojson(self):
        raw = self.cleaned_data.get("geojson") or ""
        if not str(raw).strip():
            raise forms.ValidationError("Nakreslete polygon na mapě.")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Neplatný GeoJSON.") from exc
        return json.dumps(data, ensure_ascii=False)

class ActivityItemForm(forms.ModelForm):
    class Meta:
        model = ActivityItem
        fields = (
            "shift",
            "location",
            "activity_type",
            "vehicle",
            "starts_at",
            "ends_at",
            "sort_order",
            "note",
        )
        widgets = {
            "starts_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "ends_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "note": forms.TextInput(attrs={"autocomplete": "off"}),
        }

    def __init__(self, *args, employee=None, day=None, shifts=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee = employee
        self.day = day
        self.fields["starts_at"].input_formats = [
            "%Y-%m-%dT%H:%M",
            "%d.%m.%Y %H:%M",
            "%Y-%m-%d %H:%M:%S",
        ]
        self.fields["ends_at"].input_formats = list(
            self.fields["starts_at"].input_formats
        )
        shift_qs = Shift.objects.none()
        if shifts is not None:
            shift_qs = Shift.objects.filter(pk__in=[s.pk for s in shifts])
        self.fields["shift"].queryset = shift_qs.select_related(
            "shift_type", "workplace"
        )
        self.fields["location"].queryset = _locations_for_choice()
        self.fields["location"].required = False
        self.fields["location"].empty_label = "— bez lokality —"
        self.fields["location"].label_from_instance = (
            lambda obj: obj.hierarchy_label()
        )
        self.fields["activity_type"].queryset = ActivityType.objects.filter(
            is_active=True
        ).order_by("sort_order", "name")
        self.fields["vehicle"].queryset = Vehicle.objects.filter(
            is_active=True
        ).order_by("plate")
        self.fields["vehicle"].required = False
        self.fields["vehicle"].empty_label = _vehicle_empty_label()
        self.fields["vehicle"].label_from_instance = (
            lambda obj: str(obj)
        )
        self.fields["expected_version"] = forms.IntegerField(
            required=False, widget=forms.HiddenInput()
        )
        if self.instance and self.instance.pk:
            self.fields["expected_version"].initial = self.instance.version

    def clean(self):
        cleaned = super().clean()
        tz = timezone.get_current_timezone()
        for key in ("starts_at", "ends_at"):
            value = cleaned.get(key)
            if value is not None and timezone.is_naive(value):
                cleaned[key] = timezone.make_aware(value, tz)
        start = cleaned.get("starts_at")
        end = cleaned.get("ends_at")
        if start and end and end <= start:
            self.add_error("ends_at", "Konec musí být později než začátek.")
        return cleaned


class DayPlanFilterForm(forms.Form):
    day = forms.DateField(
        label="Den",
        widget=forms.DateInput(
            attrs={
                "type": "date",
                "onchange": "this.form.submit();",
            }
        ),
    )
    workplace = forms.ModelChoiceField(
        label="Pracoviště",
        queryset=Workplace.objects.none(),
        required=False,
        empty_label="— zvolte pracoviště —",
    )
    employee = forms.ModelChoiceField(
        label="Zaměstnanec",
        queryset=Employee.objects.none(),
        required=False,
        empty_label="— všichni / detail —",
    )

    def __init__(
        self,
        *args,
        employee_queryset=None,
        workplace_queryset=None,
        workplace_counts: dict[int, int] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        wqs = workplace_queryset
        if wqs is None:
            wqs = Workplace.objects.filter(is_active=True)
        self.fields["workplace"].queryset = wqs.order_by("name")
        counts = workplace_counts or {}
        self.fields["workplace"].label_from_instance = (
            lambda wp, _c=counts: f"{wp.name} ({_c.get(wp.pk, 0)})"
        )
        eqs = employee_queryset
        if eqs is None:
            eqs = Employee.objects.filter(is_active=True)
        self.fields["employee"].queryset = eqs.order_by(
            "last_name", "first_name"
        )


class SlotRowForm(forms.Form):
    """Jeden řádek v hodinové buňce (max 10 na slot)."""

    item_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    location = forms.ModelChoiceField(
        label="Lokalita",
        queryset=ActivityLocation.objects.none(),
        required=False,
        empty_label="— bez lokality —",
    )
    activity_type = forms.ModelChoiceField(
        label="Typ",
        queryset=ActivityType.objects.none(),
        required=False,
    )
    vehicle = forms.ModelChoiceField(
        label="Vozidlo",
        queryset=Vehicle.objects.none(),
        required=False,
        empty_label="— bez vozidla —",
    )
    time_from = forms.TimeField(
        label="Od",
        required=False,
        widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        input_formats=["%H:%M", "%H:%M:%S"],
    )
    time_to = forms.TimeField(
        label="Do",
        required=False,
        widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        input_formats=["%H:%M", "%H:%M:%S"],
    )
    note = forms.CharField(
        label="Očekávání",
        required=False,
        max_length=4000,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "autocomplete": "off",
                "class": "activity-slot-note",
                "placeholder": "Popis / očekávání…",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].queryset = _locations_for_choice()
        self.fields["location"].label_from_instance = (
            lambda obj: obj.hierarchy_label()
        )
        self.fields["activity_type"].queryset = ActivityType.objects.filter(
            is_active=True
        ).order_by("sort_order", "name")
        self.fields["activity_type"].empty_label = "— zvolte typ —"
        self.fields["vehicle"].queryset = Vehicle.objects.filter(
            is_active=True
        ).order_by("plate")
        self.fields["vehicle"].empty_label = _vehicle_empty_label()
        self.fields["vehicle"].label_from_instance = lambda obj: str(obj)

    def clean(self):
        cleaned = super().clean()
        # Prázdný řádek (nic nevyplněno) je OK — při uložení se přeskočí.
        has_anything = bool(
            cleaned.get("location")
            or cleaned.get("activity_type")
            or cleaned.get("vehicle")
            or (cleaned.get("note") or "").strip()
            or cleaned.get("item_id")
            or cleaned.get("time_from")
            or cleaned.get("time_to")
        )
        if has_anything and not cleaned.get("activity_type"):
            self.add_error("activity_type", "Zvolte typ činnosti.")
        t_from = cleaned.get("time_from")
        t_to = cleaned.get("time_to")
        if (t_from is None) ^ (t_to is None):
            self.add_error(
                "time_from",
                "Vyplňte Od i Do, nebo obě pole nechte prázdná (celá hodina).",
            )
        elif t_from is not None and t_to is not None and t_to <= t_from:
            self.add_error("time_to", "Do musí být později než Od.")
        return cleaned


class DayTaskForm(forms.Form):
    """Denní úkol mimo hodinovou mřížku."""

    location = forms.ModelChoiceField(
        label="Lokalita",
        queryset=ActivityLocation.objects.none(),
        required=False,
        empty_label="— bez lokality —",
    )
    activity_type = forms.ModelChoiceField(
        label="Typ",
        queryset=ActivityType.objects.none(),
        required=True,
    )
    vehicle = forms.ModelChoiceField(
        label="Vozidlo",
        queryset=Vehicle.objects.none(),
        required=False,
        empty_label="— bez vozidla —",
    )
    note = forms.CharField(
        label="Poznámka",
        required=False,
        max_length=4000,
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "autocomplete": "off",
                "class": "activity-day-task-note",
                "placeholder": "Popis úkolu, počet kontrol, poznámky…",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].queryset = _locations_for_choice()
        self.fields["location"].label_from_instance = (
            lambda obj: obj.hierarchy_label()
        )
        self.fields["activity_type"].queryset = ActivityType.objects.filter(
            is_active=True
        ).order_by("sort_order", "name")
        self.fields["activity_type"].empty_label = "— zvolte typ —"
        self.fields["vehicle"].queryset = Vehicle.objects.filter(
            is_active=True
        ).order_by("plate")
        self.fields["vehicle"].empty_label = _vehicle_empty_label()
        self.fields["vehicle"].label_from_instance = lambda obj: str(obj)


SLOT_MAX_ITEMS = 10


class SlotMetaForm(forms.Form):
    starts_at = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={"type": "hidden"}, format="%Y-%m-%dT%H:%M"
        ),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"],
    )
    ends_at = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={"type": "hidden"}, format="%Y-%m-%dT%H:%M"
        ),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"],
    )

    def clean(self):
        cleaned = super().clean()
        tz = timezone.get_current_timezone()
        for key in ("starts_at", "ends_at"):
            value = cleaned.get(key)
            if value is not None and timezone.is_naive(value):
                cleaned[key] = timezone.make_aware(value, tz)
        start = cleaned.get("starts_at")
        end = cleaned.get("ends_at")
        if start and end and end <= start:
            self.add_error("ends_at", "Konec musí být později než začátek.")
        return cleaned


class PreferenceRowForm(forms.Form):
    location = forms.ModelChoiceField(
        label="Lokalita",
        queryset=ActivityLocation.objects.none(),
        required=False,
    )
    frequency = forms.IntegerField(
        label="Četnost",
        min_value=1,
        initial=1,
        required=False,
    )
    sort_order = forms.IntegerField(
        label="Pořadí",
        min_value=0,
        initial=100,
        required=False,
    )
    default_activity_type = forms.ModelChoiceField(
        label="Typ",
        queryset=ActivityType.objects.none(),
        required=False,
        empty_label="— výchozí —",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].queryset = _locations_for_choice()
        self.fields["location"].label_from_instance = (
            lambda obj: obj.hierarchy_label()
        )
        self.fields["default_activity_type"].queryset = (
            ActivityType.objects.filter(is_active=True).order_by(
                "sort_order", "name"
            )
        )
