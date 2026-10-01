from django.contrib import admin

from .models import Vehicle, VehicleDocument, VehicleDocumentType


class VehicleDocumentInline(admin.TabularInline):
    model = VehicleDocument
    extra = 0
    fields = (
        "document_type",
        "number",
        "valid_from",
        "valid_until",
        "issued_by",
        "is_active",
        "notes",
    )


@admin.register(VehicleDocumentType)
class VehicleDocumentTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "requires_number",
        "warn_days_before",
        "sort_order",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    prepopulated_fields = {"code": ("name",)}
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "code",
                    "name",
                    "description",
                    "requires_number",
                    "warn_days_before",
                    "sort_order",
                    "is_active",
                ),
                "description": (
                    "Číselník typů dokladů vozidel (STK, pojistka…). "
                    "Upozornění před expirací řídí počet dní."
                ),
            },
        ),
    )


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("plate", "name", "responsible", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("plate", "name", "responsible__last_name")
    autocomplete_fields = ("responsible",)
    inlines = [VehicleDocumentInline]
