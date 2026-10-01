from django.contrib import admin

from .models import EmployeeWorkplace, Workplace


class EmployeeWorkplaceInline(admin.TabularInline):
    model = EmployeeWorkplace
    extra = 0
    autocomplete_fields = ("employee",)


@admin.register(Workplace)
class WorkplaceAdmin(admin.ModelAdmin):
    list_display = ("name", "workplace_type", "address", "is_active")
    list_filter = ("is_active", "workplace_type")
    search_fields = ("name", "address")
    readonly_fields = ("created_at", "updated_at")
    inlines = [EmployeeWorkplaceInline]


@admin.register(EmployeeWorkplace)
class EmployeeWorkplaceAdmin(admin.ModelAdmin):
    list_display = ("employee", "workplace", "valid_from", "valid_to")
    list_filter = ("workplace",)
    search_fields = (
        "employee__last_name",
        "employee__first_name",
        "employee__internal_number",
        "workplace__name",
    )
    autocomplete_fields = ("employee", "workplace")
