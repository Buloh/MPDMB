"""Testy přehledu směn dne a kalendáře napříč pracovišti."""

from __future__ import annotations

from datetime import date, datetime, time

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.employees.models import Employee, Employment
from apps.shifts.models import Shift, ShiftType
from apps.workplaces.models import EmployeeWorkplace, Workplace


class DayRosterAndCalendarTests(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="roster_admin",
            password="adminpass1",
            is_staff=True,
            is_superuser=True,
        )
        self.employee = Employee.objects.create(
            first_name="Petr",
            last_name="Roster",
            internal_number="RST001",
        )
        self.workplace = Workplace.objects.create(
            name="Parkoviste Roster",
            address="Test R",
        )
        self.other_wp = Workplace.objects.create(
            name="Jine WP",
            address="Test J",
        )
        EmployeeWorkplace.objects.create(
            employee=self.employee,
            workplace=self.workplace,
            valid_from=date(2026, 1, 1),
        )
        Employment.objects.create(
            employee=self.employee,
            started_on=date(2026, 1, 1),
            is_active=True,
        )
        self.day = date(2026, 10, 5)
        self.shift_type = ShiftType.objects.filter(
            kind=ShiftType.Kind.WORK, counts_as_work=True, is_active=True
        ).first()
        if self.shift_type is None:
            self.shift_type = ShiftType.objects.create(
                code="R",
                name="Ranni",
                kind=ShiftType.Kind.WORK,
                counts_as_work=True,
                is_active=True,
                start_time=time(8, 0),
                end_time=time(14, 0),
            )
        tz = timezone.get_current_timezone()
        self.shift = Shift.objects.create(
            employee=self.employee,
            workplace=self.workplace,
            shift_type=self.shift_type,
            starts_at=timezone.make_aware(
                datetime.combine(self.day, time(8, 0)), tz
            ),
            ends_at=timezone.make_aware(
                datetime.combine(self.day, time(14, 0)), tz
            ),
            status=Shift.Status.PUBLISHED,
        )

    def test_default_view_shows_day_roster_not_auto_workplace(self):
        from .day_roster import (
            work_shifts_roster_for_day,
            workplace_shift_counts_for_day,
        )

        roster = work_shifts_roster_for_day(self.staff, self.day)
        self.assertEqual(len(roster), 1)
        self.assertEqual(roster[0].employee.pk, self.employee.pk)
        self.assertEqual(roster[0].workplace.pk, self.workplace.pk)
        counts = workplace_shift_counts_for_day(self.staff, self.day)
        self.assertEqual(counts.get(self.workplace.pk), 1)
        self.assertNotIn(self.other_wp.pk, counts)

        self.client.login(username="roster_admin", password="adminpass1")
        response = self.client.get(
            reverse("activity_day") + f"?day={self.day.isoformat()}"
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Směny dne", html)
        self.assertIn("Roster Petr", html)
        self.assertIn("Parkoviste Roster", html)
        self.assertNotIn("Rozvrh ·", html)
        self.assertContains(response, "Parkoviste Roster (1)")

    def test_calendar_markers_without_workplace_filter(self):
        from .calendar_month import activity_month_markers

        markers = activity_month_markers(
            self.staff, None, self.day.year, self.day.month
        )
        self.assertTrue(markers.get(self.day, {}).get("has_shift"))
        self.assertEqual(markers[self.day]["shift_count"], 1)

        markers_emp = activity_month_markers(
            self.staff,
            None,
            self.day.year,
            self.day.month,
            employee=self.employee,
        )
        self.assertTrue(markers_emp[self.day]["has_shift"])

    def test_vehicle_empty_label_without_fleet(self):
        from .forms import VEHICLE_EMPTY_NO_FLEET, SlotRowForm

        form = SlotRowForm()
        self.assertEqual(form.fields["vehicle"].empty_label, VEHICLE_EMPTY_NO_FLEET)
