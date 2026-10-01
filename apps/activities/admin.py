from django.contrib import admin

from .models import ActivityLocation, ActivityPreference, ActivityType, MapCity


@admin.register(ActivityType)
class ActivityTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "travel_mode", "is_active", "sort_order")
    list_filter = ("is_active", "travel_mode")
    search_fields = ("code", "name")
    ordering = ("sort_order", "name")


@admin.register(MapCity)
class MapCityAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "center_lat",
        "center_lon",
        "default_zoom",
        "is_default",
        "is_active",
        "sort_order",
    )
    list_filter = ("is_active", "is_default")
    search_fields = ("code", "name")
    ordering = ("sort_order", "name")


@admin.register(ActivityLocation)
class ActivityLocationAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "color",
        "parent",
        "workplace",
        "is_active",
        "sort_order",
    )
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    raw_id_fields = ("workplace", "parent")
    ordering = ("sort_order", "code")


@admin.register(ActivityPreference)
class ActivityPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "location",
        "frequency",
        "sort_order",
        "default_activity_type",
    )
    list_filter = ("frequency",)
    search_fields = (
        "employee__last_name",
        "employee__first_name",
        "location__code",
    )
    raw_id_fields = ("employee", "location", "default_activity_type")
    ordering = ("employee", "sort_order")
