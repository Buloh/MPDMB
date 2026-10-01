"""Testy matic oprávnění rolí."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from apps.accounts.permission_labels import (
    delete_orphaned_content_types,
    refresh_permission_names,
)
from apps.accounts.role_permissions import (
    permission_keys_for_role,
    sync_role_group_permissions,
)
from apps.accounts.roles import ROLE_ADMIN, ROLE_MANAGER, ROLE_EMPLOYEE, ROLE_READER
from apps.core.dashboard import can_manage_directory
from apps.shifts.services import can_manage_shift_plan


class RolePermissionsTests(TestCase):
    def test_sync_admin_gets_all_permissions(self):
        counts = sync_role_group_permissions()
        total = Permission.objects.count()
        self.assertEqual(counts[ROLE_ADMIN], total)
        self.assertGreater(counts[ROLE_ADMIN], counts[ROLE_MANAGER])
        self.assertGreater(counts[ROLE_MANAGER], counts[ROLE_EMPLOYEE])
        self.assertEqual(counts[ROLE_EMPLOYEE], counts[ROLE_READER])

        admin = Group.objects.get(name=ROLE_ADMIN)
        manager = Group.objects.get(name=ROLE_MANAGER)
        admin_keys = {
            f"{p.content_type.app_label}.{p.codename}"
            for p in admin.permissions.select_related("content_type")
        }
        manager_keys = {
            f"{p.content_type.app_label}.{p.codename}"
            for p in manager.permissions.select_related("content_type")
        }
        self.assertEqual(admin.permissions.count(), total)
        self.assertIn("accounts.change_user", admin_keys)
        self.assertNotIn("accounts.change_user", manager_keys)
        self.assertIn("activities.export_activity_plan", admin_keys)
        self.assertIn("activities.export_activity_plan", manager_keys)
        self.assertTrue(manager_keys < admin_keys)

    def test_staff_without_role_cannot_manage(self):
        User = get_user_model()
        staff = User.objects.create_user(
            username="bare_staff",
            password="x",
            is_staff=True,
            is_superuser=False,
        )
        self.assertFalse(can_manage_directory(staff))
        self.assertFalse(can_manage_shift_plan(staff))

        Group.objects.get_or_create(name=ROLE_MANAGER)
        sync_role_group_permissions()
        staff.groups.add(Group.objects.get(name=ROLE_MANAGER))
        staff = User.objects.get(pk=staff.pk)
        self.assertTrue(can_manage_directory(staff))
        self.assertTrue(can_manage_shift_plan(staff))

    def test_permission_keys_employee_are_view_only(self):
        keys = permission_keys_for_role(ROLE_EMPLOYEE)
        self.assertTrue(keys)
        for key in keys:
            self.assertIn(".view_", key)
            self.assertNotIn(".add_", key)
            self.assertNotIn(".change_", key)
            self.assertNotIn(".delete_", key)

    def test_refresh_permission_names_are_czech(self):
        refresh_permission_names()
        session_view = Permission.objects.get(
            content_type__app_label="sessions", codename="view_session"
        )
        self.assertTrue(session_view.name.startswith("Zobrazit: "))
        self.assertNotIn("Can view", session_view.name)
        self.assertNotIn("content type", session_view.name.lower())

        ct_view = Permission.objects.get(
            content_type__app_label="contenttypes",
            codename="view_contenttype",
        )
        self.assertTrue(ct_view.name.startswith("Zobrazit: "))
        self.assertNotIn("content type", ct_view.name.lower())

        export = Permission.objects.get(codename="export_activity_plan")
        self.assertEqual(export.name, "Exportovat plán činností")

    def test_delete_orphaned_content_types(self):
        orphan = ContentType.objects.create(
            app_label="core", model="mealallowancesettings_orphan_test"
        )
        Permission.objects.create(
            content_type=orphan,
            codename="view_mealallowancesettings_orphan_test",
            name="Can view orphan",
        )
        deleted = delete_orphaned_content_types()
        self.assertGreaterEqual(deleted, 1)
        self.assertFalse(ContentType.objects.filter(pk=orphan.pk).exists())


class AdminStaffAutoTests(TestCase):
    def test_admin_group_sets_is_staff(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="future_admin",
            password="x",
            is_staff=False,
            is_superuser=False,
        )
        group, _ = Group.objects.get_or_create(name=ROLE_ADMIN)
        user.groups.add(group)
        user.refresh_from_db()
        self.assertTrue(user.is_staff)

    def test_manager_group_does_not_set_is_staff(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="future_mgr",
            password="x",
            is_staff=False,
            is_superuser=False,
        )
        group, _ = Group.objects.get_or_create(name=ROLE_MANAGER)
        user.groups.add(group)
        user.refresh_from_db()
        self.assertFalse(user.is_staff)


class AssignEmployeeRoleCommandTests(TestCase):
    def test_assigns_employee_group_to_linked_user(self):
        from django.core.management import call_command

        from apps.employees.models import Employee

        User = get_user_model()
        user = User.objects.create_user(username="emp_linked", password="x")
        Employee.objects.create(
            first_name="Anna",
            last_name="Testova",
            internal_number="EMP-ROLE-1",
            user=user,
        )
        self.assertFalse(user.groups.filter(name=ROLE_EMPLOYEE).exists())
        call_command("assign_employee_role")
        user.refresh_from_db()
        self.assertTrue(user.groups.filter(name=ROLE_EMPLOYEE).exists())
        self.assertEqual(user.groups.count(), 1)

    def test_username_flag_assigns_without_employee_card(self):
        from django.core.management import call_command

        User = get_user_model()
        user = User.objects.create_user(username="solo_emp", password="x")
        call_command("assign_employee_role", username="solo_emp")
        user.refresh_from_db()
        self.assertTrue(user.groups.filter(name=ROLE_EMPLOYEE).exists())

    def test_skips_user_with_other_role_unless_replace(self):
        from django.core.management import call_command

        User = get_user_model()
        user = User.objects.create_user(username="has_mgr", password="x")
        mgr, _ = Group.objects.get_or_create(name=ROLE_MANAGER)
        emp, _ = Group.objects.get_or_create(name=ROLE_EMPLOYEE)
        user.groups.set([mgr])
        call_command("assign_employee_role", username="has_mgr")
        user.refresh_from_db()
        self.assertTrue(user.groups.filter(pk=mgr.pk).exists())
        self.assertFalse(user.groups.filter(pk=emp.pk).exists())
        call_command("assign_employee_role", username="has_mgr", replace=True)
        user.refresh_from_db()
        self.assertEqual(list(user.groups.values_list("name", flat=True)), [ROLE_EMPLOYEE])


class UserAdminPermissionsFormTests(TestCase):
    def test_initial_merges_group_permissions_into_selected(self):
        from apps.accounts.admin import CzechUserChangeForm
        from apps.accounts.role_permissions import sync_role_group_permissions

        sync_role_group_permissions()
        User = get_user_model()
        user = User.objects.create_user(username="perm_view", password="x")
        group = Group.objects.get(name=ROLE_EMPLOYEE)
        user.groups.add(group)
        form = CzechUserChangeForm(instance=user)
        initial_ids = set(form.initial.get("user_permissions") or [])
        group_ids = set(group.permissions.values_list("pk", flat=True))
        self.assertTrue(group_ids)
        self.assertTrue(group_ids <= initial_ids)
        self.assertEqual(user.user_permissions.count(), 0)
        self.assertEqual(form.fields["role"].initial, group)

    def test_clean_stores_only_exceptions(self):
        from apps.accounts.admin import user_permission_exceptions
        from apps.accounts.role_permissions import sync_role_group_permissions

        sync_role_group_permissions()
        User = get_user_model()
        user = User.objects.create_user(username="perm_exc", password="x")
        group = Group.objects.get(name=ROLE_EMPLOYEE)
        user.groups.add(group)
        extra = Permission.objects.exclude(
            pk__in=group.permissions.values_list("pk", flat=True)
        ).first()
        self.assertIsNotNone(extra)
        selected = list(group.permissions.all()) + [extra]
        cleaned = user_permission_exceptions(
            instance=user,
            groups=[group],
            selected=selected,
        )
        self.assertEqual([p.pk for p in cleaned], [extra.pk])

    def test_save_keeps_single_role(self):
        from apps.accounts.admin import CzechUserChangeForm, _apply_role_to_user
        from apps.accounts.role_permissions import sync_role_group_permissions

        sync_role_group_permissions()
        User = get_user_model()
        user = User.objects.create_user(username="one_role", password="x")
        emp = Group.objects.get(name=ROLE_EMPLOYEE)
        mgr = Group.objects.get(name=ROLE_MANAGER)
        user.groups.set([emp, mgr])
        form = CzechUserChangeForm(instance=user)
        self.assertEqual(form.fields["role"].initial, mgr)
        _apply_role_to_user(user, emp)
        user.refresh_from_db()
        self.assertEqual(user.groups.count(), 1)
        self.assertEqual(user.groups.get().name, ROLE_EMPLOYEE)

    def test_group_permissions_json(self):
        from django.test import Client

        from apps.accounts.role_permissions import sync_role_group_permissions

        sync_role_group_permissions()
        User = get_user_model()
        admin_user = User.objects.create_superuser(
            username="json_admin", password="x"
        )
        group = Group.objects.get(name=ROLE_EMPLOYEE)
        client = Client()
        client.force_login(admin_user)
        url = reverse("admin:accounts_user_group_permissions")
        response = client.get(url, {"group": group.pk})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("permissions", data)
        self.assertGreater(len(data["permissions"]), 0)
        self.assertIn("id", data["permissions"][0])
        self.assertIn("label", data["permissions"][0])
