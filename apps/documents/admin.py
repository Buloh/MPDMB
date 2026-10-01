from django.contrib import admin

from .models import DocumentTemplate, DocumentTemplateVersion, StoredDocument


class DocumentTemplateVersionInline(admin.TabularInline):
    model = DocumentTemplateVersion
    extra = 0
    readonly_fields = ("version_number", "file", "uploaded_by", "created_at", "notes")
    can_delete = False


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "scope", "is_active", "updated_at")
    list_filter = ("scope", "is_active")
    search_fields = ("name",)
    inlines = [DocumentTemplateVersionInline]


@admin.register(DocumentTemplateVersion)
class DocumentTemplateVersionAdmin(admin.ModelAdmin):
    list_display = ("template", "version_number", "uploaded_by", "created_at")
    list_filter = ("template__scope",)
    search_fields = ("template__name", "notes")
    readonly_fields = ("created_at",)


@admin.register(StoredDocument)
class StoredDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "employee",
        "vehicle",
        "is_active",
        "created_by",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = (
        "title",
        "employee__last_name",
        "employee__first_name",
        "vehicle__plate",
    )
    autocomplete_fields = ("employee", "vehicle")
    raw_id_fields = ("template_version",)
    readonly_fields = ("created_at", "missing_placeholders")
