from django.contrib import admin
from django.contrib.auth.models import AbstractBaseUser

from apps.accounts.roles import ROLE_ADMIN

from .models import (
    EmployeeLeaveSettings,
    LeaveEntitlement,
    LeavePolicySettings,
)

_DEADLINE_FIELDS = (
    "preferred_use_by",
    "statutory_latest_use_by",
    "deadlines_manual",
)


def _can_edit_entitlement_deadlines(user: AbstractBaseUser) -> bool:
    """Ruční lhůty nároku smí měnit jen administrátor nebo superuser."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name=ROLE_ADMIN).exists()


@admin.register(LeavePolicySettings)
class LeavePolicySettingsAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "default_weeks_wage",
        "default_weeks_salary",
        "allow_carryover",
        "enforce_continuous_block",
        "continuous_count_holidays",
        "updated_at",
    )
    fields = (
        "default_weeks_wage",
        "default_weeks_salary",
        "carryover_min_weeks_kept",
        "continuous_min_days",
        "continuous_count_holidays",
        "allow_carryover",
        "enforce_continuous_block",
        "prefer_older_entitlement",
        "warn_unused_carryover",
        "block_overlap_with_work_shifts",
        "allow_half_day",
        "updated_at",
    )
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not LeavePolicySettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = LeavePolicySettings.load()
        from django.shortcuts import redirect
        from django.urls import reverse

        return redirect(
            reverse(
                f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change",
                args=[obj.pk],
            )
        )


@admin.register(EmployeeLeaveSettings)
class EmployeeLeaveSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "employment",
        "extra_weeks",
        "allow_carryover",
        "allow_half_day",
        "enforce_continuous_block",
    )
    search_fields = (
        "employment__employee__last_name",
        "employment__employee__internal_number",
    )


@admin.register(LeaveEntitlement)
class LeaveEntitlementAdmin(admin.ModelAdmin):
    list_display = (
        "employment",
        "year",
        "accrued_minutes",
        "entitled_minutes",
        "carried_in_minutes",
        "planned_minutes",
        "taken_minutes",
        "preferred_use_by",
        "statutory_latest_use_by",
        "deadlines_manual",
        "must_use_by",
    )
    list_filter = ("year", "deadlines_manual")
    search_fields = (
        "employment__employee__last_name",
        "employment__employee__internal_number",
    )
    readonly_fields = ("must_use_by", "source_note", "updated_at")
    fields = (
        "employment",
        "year",
        "accrued_minutes",
        "entitled_minutes",
        "carried_in_minutes",
        "planned_minutes",
        "taken_minutes",
        "preferred_use_by",
        "statutory_latest_use_by",
        "deadlines_manual",
        "must_use_by",
        "source_note",
        "updated_at",
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not _can_edit_entitlement_deadlines(request.user):
            for name in _DEADLINE_FIELDS:
                if name not in readonly:
                    readonly.append(name)
        return readonly

    def save_model(self, request, obj, form, change):
        can_edit = _can_edit_entitlement_deadlines(request.user)
        if change and not can_edit:
            previous = LeaveEntitlement.objects.filter(pk=obj.pk).values(
                *_DEADLINE_FIELDS
            ).first()
            if previous:
                for name in _DEADLINE_FIELDS:
                    setattr(obj, name, previous[name])
        elif change and can_edit and not obj.deadlines_manual:
            if (
                "preferred_use_by" in form.changed_data
                or "statutory_latest_use_by" in form.changed_data
            ):
                obj.deadlines_manual = True
        super().save_model(request, obj, form, change)
