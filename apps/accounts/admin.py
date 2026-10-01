from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.contrib.auth.models import Group, Permission
from django.http import JsonResponse
from django.urls import path, reverse
from django.utils.html import format_html

from .models import User
from .roles import ALL_ROLES, ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_READER
from .staff_sync import ensure_staff_for_admin_role

ROLE_PRIORITY = (ROLE_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE, ROLE_READER)

_FIELD_LABELS = {
    "username": "Uživatelské jméno",
    "password": "Heslo",
    "first_name": "Jméno",
    "last_name": "Příjmení",
    "email": "E-mail",
    "is_staff": "Přístup do administrace",
    "is_active": "Aktivní",
    "is_superuser": "Superuživatel",
    "role": "Role",
    "user_permissions": "Uživatelská oprávnění",
    "last_login": "Poslední přihlášení",
    "date_joined": "Datum registrace",
    "employee_link": "Zaměstnanec",
}

_FIELD_HELP = {
    "is_staff": (
        "Určuje, zda se uživatel může přihlásit do administrace. "
        "Při zařazení do role administrátor se zapne automaticky."
    ),
    "is_active": (
        "Určuje, zda je účet aktivní. Odškrtněte místo mazání účtu."
    ),
    "is_superuser": (
        "Uživatel má všechna oprávnění bez explicitního přiřazení."
    ),
    "role": (
        "Právě jedna role na účet. Po změně se oprávnění ve Vybrané "
        "ihned přepočítají. Role administrátor zapne přístup do administrace."
    ),
    "user_permissions": (
        "Vybrané = oprávnění zvolené role plus výjimky. Dostupné = zbytek. "
        "Po změně role se seznam aktualizuje hned. Do databáze se ukládají "
        "jen výjimky."
    ),
}


def role_queryset():
    return Group.objects.filter(name__in=ALL_ROLES).order_by("name")


def pick_primary_role(user: User) -> Group | None:
    by_name = {
        g.name: g
        for g in user.groups.filter(name__in=ALL_ROLES)
    }
    for name in ROLE_PRIORITY:
        if name in by_name:
            return by_name[name]
    return None


def _permission_ids_for_groups(groups) -> set[int]:
    group_list = list(groups) if groups is not None else []
    if not group_list:
        return set()
    return set(
        Permission.objects.filter(group__in=group_list)
        .values_list("pk", flat=True)
        .distinct()
    )


def user_permission_exceptions(
    *,
    instance: User | None,
    groups,
    selected,
) -> list:
    """Z vybraných oprávnění nechá jen výjimky (ne práva ze skupin)."""
    selected_list = list(selected) if selected is not None else []
    new_group_ids = _permission_ids_for_groups(groups)
    if instance is not None and instance.pk:
        old_group_ids = _permission_ids_for_groups(instance.groups.all())
        previous_user_ids = set(
            instance.user_permissions.values_list("pk", flat=True)
        )
    else:
        old_group_ids = set()
        previous_user_ids = set()
    selected_ids = {perm.pk for perm in selected_list}
    auto_from_old_groups = old_group_ids - previous_user_ids
    exception_ids = (selected_ids - new_group_ids) - auto_from_old_groups
    return [perm for perm in selected_list if perm.pk in exception_ids]


def _apply_czech_labels(form):
    for name, label in _FIELD_LABELS.items():
        if name in form.fields:
            form.fields[name].label = label
    for name, help_text in _FIELD_HELP.items():
        if name in form.fields:
            form.fields[name].help_text = help_text


def _apply_role_to_user(user: User, role: Group | None) -> None:
    if role is None:
        user.groups.clear()
    else:
        user.groups.set([role])


class CzechUserChangeForm(UserChangeForm):
    role = forms.ModelChoiceField(
        label="Role",
        queryset=Group.objects.none(),
        required=False,
        empty_label="— bez role —",
    )

    class Meta(UserChangeForm.Meta):
        model = User

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = role_queryset()
        self.fields["role"].help_text = _FIELD_HELP["role"]
        if "groups" in self.fields:
            del self.fields["groups"]
        try:
            perms_url = reverse("admin:accounts_user_group_permissions")
        except Exception:
            perms_url = ""
        self.fields["role"].widget.attrs.update(
            {"data-perms-url": perms_url, "id": "id_role"}
        )
        _apply_czech_labels(self)
        primary = (
            pick_primary_role(self.instance) if self.instance.pk else None
        )
        if not self.is_bound:
            self.fields["role"].initial = primary
            if self.instance.pk and "user_permissions" in self.fields:
                group_ids = _permission_ids_for_groups(
                    [primary] if primary else []
                )
                user_ids = set(
                    self.instance.user_permissions.values_list("pk", flat=True)
                )
                self.initial["user_permissions"] = list(group_ids | user_ids)
                self.fields["role"].widget.attrs["data-role-perm-ids"] = ",".join(
                    str(i) for i in sorted(group_ids)
                )

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        groups = [role] if role is not None else []
        selected = cleaned.get("user_permissions")
        if selected is not None:
            cleaned["user_permissions"] = user_permission_exceptions(
                instance=self.instance if self.instance.pk else None,
                groups=groups,
                selected=selected,
            )
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        role = self.cleaned_data.get("role")
        if commit:
            user.save()
            self.save_m2m()
            _apply_role_to_user(user, role)
            ensure_staff_for_admin_role(user)
        else:
            old_save_m2m = self.save_m2m

            def save_m2m():
                old_save_m2m()
                _apply_role_to_user(user, role)
                ensure_staff_for_admin_role(user)

            self.save_m2m = save_m2m
        return user


class CzechUserCreationForm(AdminUserCreationForm):
    role = forms.ModelChoiceField(
        label="Role",
        queryset=Group.objects.none(),
        required=False,
        empty_label="— bez role —",
    )

    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("username", "is_active", "is_staff")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = role_queryset()
        self.fields["role"].help_text = _FIELD_HELP["role"]
        try:
            perms_url = reverse("admin:accounts_user_group_permissions")
        except Exception:
            perms_url = ""
        self.fields["role"].widget.attrs.update(
            {"data-perms-url": perms_url, "id": "id_role"}
        )
        _apply_czech_labels(self)
        if "password1" in self.fields:
            self.fields["password1"].label = "Heslo"
        if "password2" in self.fields:
            self.fields["password2"].label = "Potvrzení hesla"
        if "is_active" in self.fields:
            self.fields["is_active"].initial = True
        if "groups" in self.fields:
            del self.fields["groups"]

    def save(self, commit=True):
        user = super().save(commit=False)
        role = self.cleaned_data.get("role")
        if commit:
            user.save()
            self.save_m2m()
            _apply_role_to_user(user, role)
            ensure_staff_for_admin_role(user)
        else:
            old_save_m2m = self.save_m2m

            def save_m2m():
                old_save_m2m()
                _apply_role_to_user(user, role)
                ensure_staff_for_admin_role(user)

            self.save_m2m = save_m2m
        return user


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = CzechUserChangeForm
    add_form = CzechUserCreationForm
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_active",
    )
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)
    filter_horizontal = ("user_permissions",)
    readonly_fields = ("employee_link", "last_login", "date_joined")

    class Media:
        js = ("mpdmb/js/admin_user_role.js",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            "Osobní údaje",
            {
                "description": (
                    "Jméno, příjmení a e-mail se berou ze zaměstnance. "
                    "U zaměstnance vyplňte údaje a v poli Účet přiřaďte "
                    "tohoto uživatele — po uložení se sem zkopírují."
                ),
                "fields": ("employee_link",),
            },
        ),
        (
            "Oprávnění",
            {
                "description": (
                    "Účet má nejvýše jednu roli. Po změně role se Vybraná "
                    "oprávnění ihned přepočítají. Do databáze se ukládají "
                    "jen výjimky navíc."
                ),
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "role",
                    "user_permissions",
                ),
            },
        ),
        ("Důležitá data", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "usable_password",
                    "password1",
                    "password2",
                    "is_active",
                    "is_staff",
                    "role",
                ),
            },
        ),
    )

    def get_urls(self):
        info = self.opts.app_label, self.opts.model_name
        custom = [
            path(
                "group-permissions/",
                self.admin_site.admin_view(self.group_permissions_view),
                name="%s_%s_group_permissions" % info,
            ),
        ]
        return custom + super().get_urls()

    def group_permissions_view(self, request):
        group_id = (request.GET.get("group") or "").strip()
        if not group_id:
            return JsonResponse({"permissions": []})
        group = Group.objects.filter(
            pk=group_id, name__in=ALL_ROLES
        ).first()
        if group is None:
            return JsonResponse({"permissions": []})
        perms = (
            group.permissions.select_related("content_type")
            .order_by("content_type__app_label", "codename")
        )
        return JsonResponse(
            {
                "permissions": [
                    {"id": p.pk, "label": p.name} for p in perms
                ]
            }
        )

    @admin.display(description="Zaměstnanec")
    def employee_link(self, obj):
        if obj is None or not obj.pk:
            return "—"
        employee = getattr(obj, "employee_profile", None)
        if employee is None:
            return (
                "Nepřiřazen — jméno nastavte u zaměstnance a v poli Účet "
                "vyberte tento účet."
            )
        url = reverse("admin:employees_employee_change", args=[employee.pk])
        return format_html('<a href="{}">{}</a>', url, employee)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        for name, label in _FIELD_LABELS.items():
            if name in form.base_fields:
                form.base_fields[name].label = label
        for name, help_text in _FIELD_HELP.items():
            if name in form.base_fields:
                form.base_fields[name].help_text = help_text
        return form

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        ensure_staff_for_admin_role(form.instance)
