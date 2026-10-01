from django.contrib import admin

from .models import ShiftType


@admin.register(ShiftType)
class ShiftTypeAdmin(admin.ModelAdmin):
    list_display = (
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
    list_filter = ("is_active", "kind", "counts_as_work", "applies_on_holiday")
    search_fields = ("code", "name")
    ordering = ("sort_order", "code")
