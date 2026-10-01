from django import forms

from .models import EmployeeWorkplace, Workplace


class WorkplaceForm(forms.ModelForm):
    class Meta:
        model = Workplace
        fields = ("name", "workplace_type", "address", "is_active")
        labels = {
            "name": "Název",
            "workplace_type": "Typ",
            "address": "Adresa",
            "is_active": "Aktivní",
        }


class EmployeeWorkplaceForm(forms.ModelForm):
    class Meta:
        model = EmployeeWorkplace
        fields = ("employee", "workplace", "valid_from", "valid_to")
        labels = {
            "employee": "Zaměstnanec",
            "workplace": "Pracoviště",
            "valid_from": "Platnost od",
            "valid_to": "Platnost do",
        }
        help_texts = {
            "valid_from": (
                "Nejdříve den nástupu zaměstnance; "
                "intervaly pracovišť se nesmí překrývat."
            ),
        }
        widgets = {
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "valid_to": forms.DateInput(attrs={"type": "date"}),
        }
