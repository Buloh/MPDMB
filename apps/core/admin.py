from django.contrib import admin

from apps.core.version import APP_NAME, APP_TITLE

from .audit_labels import object_type_label, operation_label
from .models import AuditEvent

admin.site.site_header = APP_TITLE
admin.site.site_title = APP_NAME
admin.site.index_title = "Administrace (účty a číselníky)"


class OperationCzechFilter(admin.SimpleListFilter):
    title = "operace"
    parameter_name = "operation"

    def lookups(self, request, model_admin):
        codes = (
            AuditEvent.objects.order_by("operation")
            .values_list("operation", flat=True)
            .distinct()
        )
        return sorted(
            ((code, operation_label(code)) for code in codes),
            key=lambda item: item[1].lower(),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(operation=value)
        return queryset


class ObjectTypeCzechFilter(admin.SimpleListFilter):
    title = "typ objektu"
    parameter_name = "object_type"

    def lookups(self, request, model_admin):
        codes = (
            AuditEvent.objects.order_by("object_type")
            .values_list("object_type", flat=True)
            .distinct()
        )
        return sorted(
            ((code, object_type_label(code)) for code in codes),
            key=lambda item: item[1].lower(),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(object_type=value)
        return queryset


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "operation_cs",
        "object_type_cs",
        "object_id",
        "user",
    )
    list_filter = (OperationCzechFilter, ObjectTypeCzechFilter)
    search_fields = ("object_id", "detail", "user__username", "operation", "object_type")
    readonly_fields = (
        "user",
        "created_at",
        "operation_cs",
        "operation_code",
        "object_type_cs",
        "object_type_code",
        "object_id",
        "detail",
    )
    fields = (
        "created_at",
        "user",
        "operation_cs",
        "operation_code",
        "object_type_cs",
        "object_type_code",
        "object_id",
        "detail",
    )

    @admin.display(description="Operace", ordering="operation")
    def operation_cs(self, obj):
        return operation_label(obj.operation)

    @admin.display(description="Typ objektu", ordering="object_type")
    def object_type_cs(self, obj):
        return object_type_label(obj.object_type)

    @admin.display(description="Kód operace (technický)")
    def operation_code(self, obj):
        return obj.operation

    @admin.display(description="Kód typu (technický)")
    def object_type_code(self, obj):
        return obj.object_type

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
