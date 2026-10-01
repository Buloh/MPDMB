"""Formuláře panelu Dokumenty."""

from __future__ import annotations

from django import forms

from .models import DocumentTemplate
from .placeholders import placeholders_for_scope


class DocumentTemplateCreateForm(forms.Form):
    name = forms.CharField(label="Název", max_length=160)
    scope = forms.ChoiceField(
        label="Okruh",
        choices=DocumentTemplate.Scope.choices,
    )
    file = forms.FileField(
        label="Soubor .docx (volitelné)",
        required=False,
        help_text="Bez souboru se založí prázdná Word šablona.",
    )

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if uploaded is None:
            return uploaded
        name = (uploaded.name or "").lower()
        if not name.endswith(".docx"):
            raise forms.ValidationError("Povoleny jsou jen soubory .docx.")
        return uploaded


class DocumentTemplateVersionForm(forms.Form):
    file = forms.FileField(label="Nová verze .docx")
    notes = forms.CharField(label="Poznámka", required=False, max_length=255)

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        name = (uploaded.name or "").lower()
        if not name.endswith(".docx"):
            raise forms.ValidationError("Povoleny jsou jen soubory .docx.")
        return uploaded


class AppendPlaceholderForm(forms.Form):
    placeholder_key = forms.ChoiceField(label="Placeholder")

    def __init__(self, *args, scope: str, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [
            (item.key, f"{item.label} ({item.key})")
            for item in placeholders_for_scope(scope)
        ]
        self.fields["placeholder_key"].choices = choices


class GenerateDocumentForm(forms.Form):
    template = forms.ModelChoiceField(
        label="Šablona",
        queryset=DocumentTemplate.objects.none(),
    )
    title = forms.CharField(label="Název dokumentu", required=False, max_length=200)

    def __init__(self, *args, scope: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["template"].queryset = DocumentTemplate.objects.filter(
            is_active=True,
            scope=scope,
        ).order_by("name")


class UploadStoredDocumentForm(forms.Form):
    title = forms.CharField(label="Název", max_length=200)
    file = forms.FileField(label="Soubor .docx")
    notes = forms.CharField(label="Poznámka", required=False, max_length=255)

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        name = (uploaded.name or "").lower()
        if not name.endswith(".docx"):
            raise forms.ValidationError("Povoleny jsou jen soubory .docx.")
        return uploaded
