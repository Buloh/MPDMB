"""Testy modelu přiřazení pracoviště."""

from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.employees.models import Employee, Employment
from apps.workplaces.models import EmployeeWorkplace, Workplace


class EmployeeWorkplaceModelTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            first_name="Petr",
            last_name="Test",
            internal_number="WP001",
        )
        self.workplace = Workplace.objects.create(name="Test WP")
        Employment.objects.create(
            employee=self.employee,
            started_on=date(2026, 11, 1),
            relation_type=Employment.RelationType.EMPLOYMENT,
            is_active=True,
        )

    def test_clean_rejects_valid_from_before_employment(self):
        asg = EmployeeWorkplace(
            employee=self.employee,
            workplace=self.workplace,
            valid_from=date(2026, 10, 1),
        )
        with self.assertRaises(ValidationError) as ctx:
            asg.full_clean()
        self.assertIn("valid_from", ctx.exception.message_dict)

    def test_clean_rejects_overlap(self):
        EmployeeWorkplace.objects.create(
            employee=self.employee,
            workplace=self.workplace,
            valid_from=date(2026, 11, 1),
        )
        other = Workplace.objects.create(name="Druhe WP")
        asg = EmployeeWorkplace(
            employee=self.employee,
            workplace=other,
            valid_from=date(2026, 11, 15),
        )
        with self.assertRaises(ValidationError) as ctx:
            asg.full_clean()
        self.assertIn("překrývá", str(ctx.exception))

    def test_clean_ok_from_employment_start(self):
        asg = EmployeeWorkplace(
            employee=self.employee,
            workplace=self.workplace,
            valid_from=date(2026, 11, 1),
        )
        asg.full_clean()
        asg.save()
        self.assertEqual(EmployeeWorkplace.objects.count(), 1)
