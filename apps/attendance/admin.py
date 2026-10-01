from decimal import Decimal, ROUND_HALF_UP

from django import forms
from django.contrib import admin

from .models import AbsenceType, MealAllowanceSettings


@admin.register(AbsenceType)
class AbsenceTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "accounting_kind", "is_active", "sort_order")
    list_filter = ("is_active", "accounting_kind")
    search_fields = ("code", "name")
    ordering = ("sort_order", "name")


def _hours_from_minutes(minutes: int | None) -> Decimal | None:
    if minutes is None:
        return None
    return (Decimal(minutes) / Decimal(60)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _minutes_from_hours(hours: Decimal) -> int:
    return int(
        (hours * Decimal(60)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


class MealAllowanceSettingsForm(forms.ModelForm):
    min_worked_hours = forms.DecimalField(
        label="1. stravenka od (hodiny)",
        min_value=Decimal("0.01"),
        max_digits=5,
        decimal_places=2,
        help_text=(
            "Minimální čistá potvrzená práce v jednom dni pro 1. stravenku. "
            "Např. 3,00 = tři hodiny."
        ),
    )
    second_worked_hours = forms.DecimalField(
        label="2. stravenka od (hodiny)",
        required=False,
        min_value=Decimal("0.01"),
        max_digits=5,
        decimal_places=2,
        help_text=(
            "Práh pro 2. stravenku ve stejném dni. Např. 12,00. "
            "Prázdné = nejvýše 1 stravenka za den."
        ),
    )

    class Meta:
        model = MealAllowanceSettings
        fields = ("min_worked_hours", "second_worked_hours", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["min_worked_hours"].initial = _hours_from_minutes(
                self.instance.min_worked_minutes or 180
            )
            self.fields["second_worked_hours"].initial = _hours_from_minutes(
                self.instance.second_worked_minutes
            )

    def clean(self):
        cleaned = super().clean()
        first = cleaned.get("min_worked_hours")
        second = cleaned.get("second_worked_hours")
        if first is not None and second is not None and second <= first:
            self.add_error(
                "second_worked_hours",
                "Práh 2. stravenky musí být větší než práh 1. stravenky.",
            )
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.min_worked_minutes = _minutes_from_hours(
            self.cleaned_data["min_worked_hours"]
        )
        second_hours = self.cleaned_data.get("second_worked_hours")
        obj.second_worked_minutes = (
            _minutes_from_hours(second_hours) if second_hours is not None else None
        )
        if commit:
            obj.save()
        return obj


@admin.register(MealAllowanceSettings)
class MealAllowanceSettingsAdmin(admin.ModelAdmin):
    form = MealAllowanceSettingsForm
    list_display = (
        "__str__",
        "min_worked_minutes",
        "second_worked_minutes",
        "is_active",
        "updated_at",
    )
    fields = (
        "min_worked_hours",
        "second_worked_hours",
        "is_active",
        "updated_at",
    )
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not MealAllowanceSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = MealAllowanceSettings.load()
        from django.shortcuts import redirect
        from django.urls import reverse

        return redirect(
            reverse(
                f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change",
                args=[obj.pk],
            )
        )
