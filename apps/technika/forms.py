"""Formuláře evidence vozidel."""

from __future__ import annotations

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from apps.employees.models import Employee

from .models import Vehicle, VehicleDocument, VehicleDocumentType, normalize_plate


class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ("plate", "name", "responsible", "is_active", "notes")
        labels = {
            "plate": "SPZ",
            "name": "Označení",
            "responsible": "Odpovědná osoba",
            "is_active": "Aktivní",
            "notes": "Poznámka",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsible"].queryset = Employee.objects.filter(
            is_active=True
        ).order_by("last_name", "first_name")
        self.fields["responsible"].label_from_instance = (
            lambda e: f"{e.last_name} {e.first_name} ({e.internal_number})"
        )
        self.fields["name"].required = False
        self.fields["notes"].required = False

    def clean_plate(self):
        return normalize_plate(self.cleaned_data.get("plate") or "")


class VehicleDocumentForm(forms.ModelForm):
    class Meta:
        model = VehicleDocument
        fields = (
            "document_type",
            "number",
            "valid_from",
            "valid_until",
            "issued_by",
            "notes",
            "is_active",
        )
        labels = {
            "document_type": "Typ",
            "number": "Číslo",
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
        self.fields["document_type"].queryset = (
            VehicleDocumentType.objects.filter(is_active=True).order_by(
                "sort_order", "name"
            )
        )
        self.fields["document_type"].required = False
        for name in ("valid_from", "valid_until"):
            self.fields[name].input_formats = ["%Y-%m-%d", "%d.%m.%Y"]
            self.fields[name].required = False

    def has_changed(self):
        prefix = self.add_prefix("document_type")
        raw_type = ""
        if self.data is not None:
            raw_type = (self.data.get(prefix) or "").strip()
        if not raw_type and not getattr(self.instance, "pk", None):
            return False
        return super().has_changed()

    def clean(self):
        cleaned = super().clean()
        dtype = cleaned.get("document_type")
        if not dtype:
            return cleaned
        number = (cleaned.get("number") or "").strip()
        cleaned["number"] = number
        if dtype.requires_number and not number:
            self.add_error("number", "Tento typ vyžaduje číslo.")
        valid_from = cleaned.get("valid_from")
        valid_until = cleaned.get("valid_until")
        if valid_from and valid_until and valid_until < valid_from:
            self.add_error(
                "valid_until",
                "Platnost do nesmí být dříve než platnost od.",
            )
        return cleaned


class BaseVehicleDocumentFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()


VehicleDocumentFormSet = inlineformset_factory(
    Vehicle,
    VehicleDocument,
    form=VehicleDocumentForm,
    formset=BaseVehicleDocumentFormSet,
    extra=1,
    can_delete=True,
)
