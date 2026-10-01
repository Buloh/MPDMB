"""Testy evidence vozidel a přiřazení k činnostem."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import ROLE_ADMIN
from apps.activities.models import ActivityType
from apps.activities.services import ActivityConflictError, create_activity_item
from apps.employees.models import Employee, EmployeeQualification, Employment, QualificationType
from apps.shifts.models import Shift, ShiftType
from apps.technika.models import Vehicle, VehicleDocument, VehicleDocumentType
from apps.technika.services import (
    employee_may_drive,
    vehicle_document_alerts_for_user,
)
from apps.workplaces.models import Workplace


class TechnikaVehicleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="tech_admin",
            password="test-pass-tech",
            is_staff=True,
            is_superuser=True,
        )
        Group.objects.get_or_create(name=ROLE_ADMIN)
        self.user.groups.add(Group.objects.get(name=ROLE_ADMIN))
        self.client = Client()
        self.client.login(username="tech_admin", password="test-pass-tech")

        self.driver = Employee.objects.create(
            first_name="Jan",
            last_name="Ridic",
            internal_number="T001",
            is_active=True,
        )
        self.nondriver = Employee.objects.create(
            first_name="Petr",
            last_name="Pecha",
            internal_number="T002",
            is_active=True,
        )
        Employment.objects.create(
            employee=self.driver,
            relation_type=Employment.RelationType.EMPLOYMENT,
            started_on=date(2020, 1, 1),
            is_active=True,
        )
        Employment.objects.create(
            employee=self.nondriver,
            relation_type=Employment.RelationType.EMPLOYMENT,
            started_on=date(2020, 1, 1),
            is_active=True,
        )
        license_type = QualificationType.objects.get(code="ridicsky_prukaz")
        EmployeeQualification.objects.create(
            employee=self.driver,
            qualification_type=license_type,
            number="AB123456",
            categories="B",
            valid_until=date(2030, 1, 1),
            is_active=True,
        )
        self.stk_type = VehicleDocumentType.objects.get(code="stk")
        self.workplace = Workplace.objects.create(
            name="PD Test",
            workplace_type=Workplace.WorkplaceType.PARKING_HOUSE,
            is_active=True,
        )
        self.shift_type = ShiftType.objects.filter(
            kind=ShiftType.Kind.WORK, counts_as_work=True, is_active=True
        ).first()
        if self.shift_type is None:
            self.shift_type = ShiftType.objects.create(
                code="R",
                name="Ranní",
                kind=ShiftType.Kind.WORK,
                counts_as_work=True,
                is_active=True,
                start_time=time(8, 0),
                end_time=time(14, 0),
            )
        self.activity_type = ActivityType.objects.filter(is_active=True).first()
        if self.activity_type is None:
            self.activity_type = ActivityType.objects.create(
                code="KON",
                name="Kontrola",
                is_active=True,
            )

    def _aware(self, day: date, hour: int, minute: int = 0):
        tz = timezone.get_current_timezone()
        return timezone.make_aware(datetime.combine(day, time(hour, minute)), tz)

    def _publish_shift(self, employee: Employee, day: date) -> Shift:
        starts = self._aware(day, 8)
        ends = self._aware(day, 14)
        return Shift.objects.create(
            employee=employee,
            workplace=self.workplace,
            shift_type=self.shift_type,
            starts_at=starts,
            ends_at=ends,
            status=Shift.Status.PUBLISHED,
        )

    def test_seed_document_types(self):
        self.assertTrue(VehicleDocumentType.objects.filter(code="stk").exists())
        self.assertTrue(VehicleDocumentType.objects.filter(code="pojistka").exists())

    def test_create_vehicle_with_stk(self):
        vehicle = Vehicle.objects.create(
            plate="1ab 2345",
            name="Dodávka",
            responsible=self.driver,
            is_active=True,
        )
        self.assertEqual(vehicle.plate, "1AB2345")
        VehicleDocument.objects.create(
            vehicle=vehicle,
            document_type=self.stk_type,
            number="STK-1",
            valid_until=timezone.localdate() + timedelta(days=10),
            is_active=True,
        )
        self.assertTrue(vehicle.active_documents().exists())
        response = self.client.get(reverse("vehicle_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1AB2345")

    def test_employee_may_drive(self):
        self.assertTrue(employee_may_drive(self.driver))
        self.assertFalse(employee_may_drive(self.nondriver))

    def test_assign_requires_license(self):
        vehicle = Vehicle.objects.create(
            plate="2BC3456",
            responsible=self.driver,
            is_active=True,
        )
        day = timezone.localdate()
        shift = self._publish_shift(self.nondriver, day)
        with self.assertRaises(ActivityConflictError):
            create_activity_item(
                user=self.user,
                employee=self.nondriver,
                shift=shift,
                location=None,
                activity_type=self.activity_type,
                starts_at=shift.starts_at,
                ends_at=shift.starts_at + timedelta(hours=1),
                vehicle=vehicle,
            )

    def test_assign_with_license_ok(self):
        vehicle = Vehicle.objects.create(
            plate="3CD4567",
            responsible=self.driver,
            is_active=True,
        )
        day = timezone.localdate()
        shift = self._publish_shift(self.driver, day)
        item = create_activity_item(
            user=self.user,
            employee=self.driver,
            shift=shift,
            location=None,
            activity_type=self.activity_type,
            starts_at=shift.starts_at,
            ends_at=shift.starts_at + timedelta(hours=1),
            vehicle=vehicle,
        )
        self.assertEqual(item.vehicle_id, vehicle.pk)

    def test_overlap_hard_block_and_adjacent_ok(self):
        vehicle = Vehicle.objects.create(
            plate="4DE5678",
            responsible=self.driver,
            is_active=True,
        )
        day = timezone.localdate()
        shift_a = self._publish_shift(self.driver, day)
        other = Employee.objects.create(
            first_name="Eva",
            last_name="Druha",
            internal_number="T003",
            is_active=True,
        )
        Employment.objects.create(
            employee=other,
            relation_type=Employment.RelationType.EMPLOYMENT,
            started_on=date(2020, 1, 1),
            is_active=True,
        )
        license_type = QualificationType.objects.get(code="ridicsky_prukaz")
        EmployeeQualification.objects.create(
            employee=other,
            qualification_type=license_type,
            number="CD999",
            categories="B",
            valid_until=date(2030, 1, 1),
            is_active=True,
        )
        shift_b = self._publish_shift(other, day)
        create_activity_item(
            user=self.user,
            employee=self.driver,
            shift=shift_a,
            location=None,
            activity_type=self.activity_type,
            starts_at=self._aware(day, 8),
            ends_at=self._aware(day, 10),
            vehicle=vehicle,
        )
        with self.assertRaises(ActivityConflictError):
            create_activity_item(
                user=self.user,
                employee=other,
                shift=shift_b,
                location=None,
                activity_type=self.activity_type,
                starts_at=self._aware(day, 9),
                ends_at=self._aware(day, 11),
                vehicle=vehicle,
            )
        adjacent = create_activity_item(
            user=self.user,
            employee=other,
            shift=shift_b,
            location=None,
            activity_type=self.activity_type,
            starts_at=self._aware(day, 10),
            ends_at=self._aware(day, 12),
            vehicle=vehicle,
        )
        self.assertEqual(adjacent.vehicle_id, vehicle.pk)

    def test_inactive_vehicle_blocked(self):
        vehicle = Vehicle.objects.create(
            plate="5EF6789",
            responsible=self.driver,
            is_active=False,
        )
        day = timezone.localdate()
        shift = self._publish_shift(self.driver, day)
        with self.assertRaises(ActivityConflictError):
            create_activity_item(
                user=self.user,
                employee=self.driver,
                shift=shift,
                location=None,
                activity_type=self.activity_type,
                starts_at=shift.starts_at,
                ends_at=shift.starts_at + timedelta(hours=1),
                vehicle=vehicle,
            )

    def test_document_alerts_on_home(self):
        vehicle = Vehicle.objects.create(
            plate="6FG7890",
            responsible=self.driver,
            is_active=True,
        )
        VehicleDocument.objects.create(
            vehicle=vehicle,
            document_type=self.stk_type,
            number="STK-X",
            valid_until=timezone.localdate() - timedelta(days=1),
            is_active=True,
        )
        alerts = vehicle_document_alerts_for_user(self.user)
        self.assertTrue(any(a["severity"] == "expired" for a in alerts))
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Doklady vozidel k řešení")
        self.assertContains(response, "6FG7890")
