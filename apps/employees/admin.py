from django.contrib import admin

from .models import (
    Employee,
    EmployeeQualification,
    Employment,
    QualificationType,
    WorkTimePreset,
)
from .user_sync import sync_user_from_employee


class EmploymentInline(admin.TabularInline):
    model = Employment
    extra = 0
    fields = (
        "relation_type",
        "started_on",
        "ended_on",
        "payroll_number",
        "pay_regime",
        "job_title",
        "is_active",
    )


class EmployeeQualificationInline(admin.TabularInline):
    model = EmployeeQualification
    extra = 0
    autocomplete_fields = ("qualification_type",)
    fields = (
        "qualification_type",
        "number",
        "categories",
        "valid_from",
        "valid_until",
        "issued_by",
        "is_active",
    )


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "internal_number",
        "last_name",
        "first_name",
        "job_title",
        "is_active",
        "user",
    )
    list_filter = ("is_active",)
    search_fields = (
        "internal_number",
        "first_name",
        "last_name",
        "job_title",
        "phone",
        "email",
    )
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [EmploymentInline, EmployeeQualificationInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        sync_user_from_employee(obj)


@admin.register(Employment)
class EmploymentAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "relation_type",
        "started_on",
        "ended_on",
        "payroll_number",
        "pay_regime",
        "job_title",
        "is_active",
    )
    list_filter = ("relation_type", "pay_regime", "is_active")
    search_fields = (
        "payroll_number",
        "employee__internal_number",
        "employee__last_name",
        "employee__first_name",
        "job_title",
    )
    autocomplete_fields = ("employee",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            None,
            {
                "description": (
                    "Pracovní vztah (pracovní poměr, DPP, DPČ). "
                    "Profily pracovní doby a vyrovnávací období nastavte "
                    "v aplikaci na /smeny/fond/ (včetně hromadného vytvoření)."
                ),
                "fields": (
                    "employee",
                    "relation_type",
                    "started_on",
                    "ended_on",
                    "payroll_number",
                    "pay_regime",
                    "job_title",
                    "is_active",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )


@admin.register(QualificationType)
class QualificationTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "requires_number",
        "requires_categories",
        "warn_days_before",
        "sort_order",
        "is_active",
    )
    list_filter = ("is_active", "requires_number", "requires_categories")
    search_fields = ("name", "code", "description")
    prepopulated_fields = {"code": ("name",)}
    ordering = ("sort_order", "name")
    fieldsets = (
        (
            None,
            {
                "description": (
                    "Číselník typů kvalifikací (řidičák, elektro…). "
                    "Pole „upozornit dní před expirací“ řídí varování na Přehledu."
                ),
                "fields": (
                    "name",
                    "code",
                    "description",
                    "requires_number",
                    "requires_categories",
                    "warn_days_before",
                    "sort_order",
                    "is_active",
                ),
            },
        ),
    )


@admin.register(WorkTimePreset)
class WorkTimePresetAdmin(admin.ModelAdmin):
    list_display = ("name", "weekly_minutes", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("sort_order", "name")
    fieldsets = (
        (
            None,
            {
                "description": (
                    "Předvolby týdenního úvazku pro formulář profilu na "
                    "/smeny/fond/. Běžná správa i v aplikaci "
                    "(/smeny/fond/predvolby/)."
                ),
                "fields": ("name", "weekly_minutes", "sort_order", "is_active"),
            },
        ),
    )
