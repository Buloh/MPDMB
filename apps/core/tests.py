"""Testy jádra (auditní popisky, rozcestník administrace)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.roles import ROLE_ADMIN, ROLE_EMPLOYEE
from apps.core.admin_hub import admin_hub_sections

from .audit_labels import object_type_label, operation_label


class AuditLabelsTests(SimpleTestCase):
    def test_known_operations_are_czech(self):
        self.assertEqual(
            operation_label("activity_location.create"),
            "Lokalita činnosti: vytvoření",
        )
        self.assertEqual(
            operation_label("workplace_assign"),
            "Přiřazení pracoviště",
        )
        self.assertEqual(operation_label("shift_cell_create"), "Vytvoření směny v buňce")

    def test_unknown_operation_marks_missing_map(self):
        label = operation_label("totally.unknown_op")
        self.assertIn("totally.unknown_op", label)
        self.assertIn("bez české mapy", label)

    def test_object_types(self):
        self.assertEqual(object_type_label("ActivityLocation"), "Lokalita činnosti")
        self.assertIn("bez české mapy", object_type_label("UnknownThing"))


class AdminHubTests(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="admin_hub_user",
            password="hubpass123",
            is_staff=True,
        )
        group, _ = Group.objects.get_or_create(name=ROLE_ADMIN)
        self.admin.groups.add(group)
        self.employee_user = User.objects.create_user(
            username="emp_hub_user",
            password="emppass123",
            is_staff=False,
        )
        emp_group, _ = Group.objects.get_or_create(name=ROLE_EMPLOYEE)
        self.employee_user.groups.add(emp_group)

    def test_hub_ok_for_admin(self):
        self.client.login(username="admin_hub_user", password="hubpass123")
        response = self.client.get(reverse("admin_hub"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Administrace")
        self.assertContains(response, "Uživatelé")
        self.assertContains(response, "Kompletní Django admin")

    def test_hub_forbidden_for_employee(self):
        self.client.login(username="emp_hub_user", password="emppass123")
        response = self.client.get(reverse("admin_hub"))
        self.assertEqual(response.status_code, 403)

    def test_dashboard_tile_points_to_hub(self):
        self.client.login(username="admin_hub_user", password="hubpass123")
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("admin_hub"))

    def test_admin_index_uses_mpdmb_css(self):
        self.client.login(username="admin_hub_user", password="hubpass123")
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SYNERA")
        self.assertContains(response, "mpdmb/css/admin.css")
        self.assertContains(response, "Rozcestník Administrace")

    def test_admin_hub_sections_resolve(self):
        sections = admin_hub_sections()
        self.assertGreaterEqual(len(sections), 3)
        first_url = sections[0].tiles[0].resolve_url()
        self.assertTrue(first_url.startswith("/admin/"))
