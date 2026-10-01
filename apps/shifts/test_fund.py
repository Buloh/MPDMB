from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.employees.models import (
    BalancingPeriod,
    Employee,
    Employment,
    WorkTimePreset,
    WorkTimeProfile,
)
from apps.shifts.forms import WorkTimePresetForm, WorkTimeProfileForm
from apps.shifts.holidays import holidays_for_year
from apps.shifts.models import (
    EmployeeScheduleAssignment,
    ScheduleTemplate,
    ShiftType,
)
from apps.shifts.services import (
    assign_shift_cell,
    balancing_summaries_for_month,
    build_month_matrix,
    calendar_month_fund,
    fund_summary_for_employee,
)
from apps.shifts.fund import dynamic_balancing_target_minutes
from apps.workplaces.models import EmployeeWorkplace, Workplace


class BulkFundTests(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="fond_admin",
            password="test-pass-fund",
            is_staff=True,
            is_superuser=True,
        )
        self.emp_a = Employee.objects.create(
            first_name="Adam",
            last_name="Alpha",
            internal_number="F001",
        )
        self.emp_b = Employee.objects.create(
            first_name="Bara",
            last_name="Beta",
            internal_number="F002",
        )
        Employment.objects.create(
            employee=self.emp_a,
            started_on=date(2026, 1, 1),
        )
        Employment.objects.create(
            employee=self.emp_b,
            started_on=date(2026, 1, 1),
        )

    def test_bulk_profile_and_period_for_two_employees(self):
        from apps.employees.services import (
            bulk_create_balancing_periods,
            bulk_create_work_time_profiles,
        )

        profiles = bulk_create_work_time_profiles(
            user=self.staff,
            employees=[self.emp_a, self.emp_b],
            valid_from=date(2026, 1, 1),
            statutory_weekly_minutes=2400,
            agreed_weekly_minutes=2400,
            regime=WorkTimeProfile.Regime.SINGLE,
            distribution=WorkTimeProfile.Distribution.EVEN,
        )
        self.assertEqual(len(profiles.created), 2)
        self.assertEqual(len(profiles.skipped), 0)

        periods = bulk_create_balancing_periods(
            user=self.staff,
            employees=[self.emp_a, self.emp_b],
            starts_on=date(2026, 1, 1),
            ends_on=date(2026, 6, 30),
            kind=BalancingPeriod.Kind.SCHEDULE,
            auto_target=True,
        )
        self.assertEqual(len(periods.created), 2)
        self.assertEqual(
            BalancingPeriod.objects.filter(
                starts_on=date(2026, 1, 1),
                ends_on=date(2026, 6, 30),
            ).count(),
            2,
        )

    def test_bulk_period_form_view(self):
        WorkTimeProfile.objects.create(
            employment=self.emp_a.employments.get(),
            valid_from=date(2026, 1, 1),
            statutory_weekly_minutes=2400,
            agreed_weekly_minutes=2400,
        )
        WorkTimeProfile.objects.create(
            employment=self.emp_b.employments.get(),
            valid_from=date(2026, 1, 1),
            statutory_weekly_minutes=2400,
            agreed_weekly_minutes=2400,
        )
        self.client.login(username="fond_admin", password="test-pass-fund")
        response = self.client.post(
            reverse("balancing_period_bulk_create"),
            {
                "employees": [self.emp_a.pk, self.emp_b.pk],
                "starts_on": "2026-07-01",
                "ends_on": "2026-12-31",
                "kind": BalancingPeriod.Kind.SCHEDULE,
                "auto_target": "on",
                "note": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            BalancingPeriod.objects.filter(
                starts_on=date(2026, 7, 1),
                ends_on=date(2026, 12, 31),
            ).count(),
            2,
        )

    def test_fund_list_shows_hours_and_bulk_links(self):
        WorkTimeProfile.objects.create(
            employment=self.emp_a.employments.get(),
            valid_from=date(2026, 1, 1),
            statutory_weekly_minutes=2400,
            agreed_weekly_minutes=2400,
        )
        self.client.login(username="fond_admin", password="test-pass-fund")
        response = self.client.get(reverse("work_time_profile_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "40 h")
        self.assertContains(response, "Stejné období pro více")
        self.assertContains(response, "Předvolby úvazku")
        self.assertContains(response, "Přehled úvazků")
        self.assertContains(response, "Zaměstnanci (úvazek)")


class FundUvazekShiftTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="fond_uvazek",
            password="test-pass-uv",
            is_staff=True,
            is_superuser=True,
        )
        self.employee = Employee.objects.create(
            first_name="Eva",
            last_name="Fondova",
            internal_number="U001",
        )
        self.employment = Employment.objects.create(
            employee=self.employee,
            started_on=date(2026, 1, 1),
        )
        self.workplace = Workplace.objects.create(name="Depo Uvazek")
        EmployeeWorkplace.objects.create(
            employee=self.employee,
            workplace=self.workplace,
            valid_from=date(2026, 1, 1),
        )
        self.type_r = ShiftType.objects.get(code="R")
        self.type_11 = ShiftType.objects.create(
            code="N11",
            name="Nepretrzita 11h",
            kind=ShiftType.Kind.WORK,
            start_time=time(6, 0),
            end_time=time(17, 0),
            break_minutes=0,
            counts_as_work=True,
            applies_on_holiday=True,
            sort_order=50,
        )

    def test_profile_40h_september_2026_equals_176(self):
        WorkTimeProfile.objects.create(
            employment=self.employment,
            valid_from=date(2026, 1, 1),
            statutory_weekly_minutes=2400,
            agreed_weekly_minutes=2400,
            regime=WorkTimeProfile.Regime.SINGLE,
        )
        matrix = build_month_matrix(user=self.staff, year=2026, month=9)
        row = next(r for r in matrix["rows"] if r["employee"].pk == self.employee.pk)
        self.assertEqual(row["fund"]["daily_minutes"], 8 * 60)
        self.assertEqual(row["fund"]["work_days"], 22)
        self.assertEqual(row["fund"]["holiday_weekdays"], 1)
        self.assertEqual(row["fund"]["fund_minutes"], 176 * 60)
        self.assertIn("úvazek", row["fund"]["daily_source"])

    def test_profile_375h_september_2026_equals_165(self):
        WorkTimeProfile.objects.create(
            employment=self.employment,
            valid_from=date(2026, 1, 1),
            statutory_weekly_minutes=2250,
            agreed_weekly_minutes=2250,
            regime=WorkTimeProfile.Regime.SINGLE,
        )
        matrix = build_month_matrix(user=self.staff, year=2026, month=9)
        row = next(r for r in matrix["rows"] if r["employee"].pk == self.employee.pk)
        self.assertEqual(row["fund"]["daily_minutes"], 7 * 60 + 30)
        self.assertEqual(row["fund"]["work_days"], 22)
        self.assertEqual(row["fund"]["fund_minutes"], 165 * 60)

    def test_seeded_presets_exist(self):
        names = set(
            WorkTimePreset.objects.filter(is_active=True).values_list(
                "name", flat=True
            )
        )
        self.assertTrue({"40 hodin", "38,75 hodin", "37,5 hodin"} <= names)
        self.assertEqual(
            WorkTimePreset.objects.get(name="40 hodin").weekly_minutes, 2400
        )
        self.assertEqual(
            WorkTimePreset.objects.get(name="38,75 hodin").weekly_minutes, 2325
        )
        self.assertEqual(
            WorkTimePreset.objects.get(name="37,5 hodin").weekly_minutes, 2250
        )

    def test_preset_fills_statutory_and_agreed(self):
        preset = WorkTimePreset.objects.get(name="37,5 hodin")
        form = WorkTimeProfileForm(
            data={
                "employment": self.employment.pk,
                "valid_from": "2026-01-01",
                "valid_to": "",
                "preset": preset.pk,
                "statutory_weekly_minutes": "2400",
                "agreed_weekly_minutes": "2400",
                "regime": WorkTimeProfile.Regime.SINGLE,
                "distribution": WorkTimeProfile.Distribution.EVEN,
                "is_active": "on",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["statutory_weekly_minutes"], 2250)
        self.assertEqual(form.cleaned_data["agreed_weekly_minutes"], 2250)
        self.assertIn("h/den", form.derived_daily_label)

    def test_manual_minutes_without_preset(self):
        form = WorkTimeProfileForm(
            data={
                "employment": self.employment.pk,
                "valid_from": "2026-01-01",
                "valid_to": "",
                "preset": "",
                "statutory_weekly_minutes": "1800",
                "agreed_weekly_minutes": "1800",
                "regime": WorkTimeProfile.Regime.SINGLE,
                "distribution": WorkTimeProfile.Distribution.EVEN,
                "is_active": "on",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["agreed_weekly_minutes"], 1800)
        self.assertIsNone(form.cleaned_data.get("preset"))

    def test_preset_crud_staff(self):
        self.client.login(username="fond_uvazek", password="test-pass-uv")
        list_url = reverse("work_time_preset_list")
        resp = self.client.get(list_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "40 hodin")

        create_url = reverse("work_time_preset_create")
        resp = self.client.post(
            create_url,
            {
                "name": "30 hodin",
                "weekly_minutes": "1800",
                "sort_order": "40",
                "is_active": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        preset = WorkTimePreset.objects.get(name="30 hodin")
        self.assertEqual(preset.weekly_minutes, 1800)

        edit_url = reverse("work_time_preset_edit", args=[preset.pk])
        resp = self.client.post(
            edit_url,
            {
                "name": "30 hodin (poloviční)",
                "weekly_minutes": "1800",
                "sort_order": "40",
                "is_active": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        preset.refresh_from_db()
        self.assertEqual(preset.name, "30 hodin (poloviční)")

        form = WorkTimePresetForm(
            data={
                "name": "20 hodin",
                "weekly_minutes": "1200",
                "sort_order": "50",
                "is_active": "on",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_morning_profile_matches_planned_on_workdays(self):
        net = self.type_r.net_minutes()
        WorkTimeProfile.objects.create(
            employment=self.employment,
            valid_from=date(2026, 1, 1),
            statutory_weekly_minutes=net * 5,
            agreed_weekly_minutes=net * 5,
            regime=WorkTimeProfile.Regime.SINGLE,
        )
        # Po–Pá včetně svátku 28.9. (svátek se počítá do fondu).
        for day_num in range(1, 31):
            day = date(2026, 9, day_num)
            if day.weekday() >= 5:
                continue
            assign_shift_cell(
                user=self.staff,
                employee=self.employee,
                workplace=self.workplace,
                day=day,
                shift_type=self.type_r,
                publish=True,
            )
        matrix = build_month_matrix(user=self.staff, year=2026, month=9)
        row = next(r for r in matrix["rows"] if r["employee"].pk == self.employee.pk)
        self.assertEqual(row["fund"]["daily_minutes"], net)
        self.assertEqual(row["planned_minutes"], row["fund"]["fund_minutes"])
        self.assertTrue(row["fund_delta_ok"])

    def test_continuous_includes_weekend_from_template(self):
        template = ScheduleTemplate.objects.create(
            name="Conti7", cycle_length=7, is_active=True
        )
        template.ensure_slots()
        for i in range(7):
            slot = template.slots.get(day_index=i)
            slot.shift_type = self.type_11
            slot.save(update_fields=["shift_type"])
        EmployeeScheduleAssignment.objects.create(
            employee=self.employee,
            template=template,
            workplace=self.workplace,
            valid_from=date(2026, 9, 1),
            cycle_anchor_date=date(2026, 8, 31),  # pondělí před 1.9. = Po 31.8.? 
            # 1.9.2026 is Tuesday. Anchor Monday 31.8.2026
        )
        # Fix anchor to Monday
        asg = EmployeeScheduleAssignment.objects.get(employee=self.employee)
        asg.cycle_anchor_date = date(2026, 8, 31)
        asg.save(update_fields=["cycle_anchor_date"])

        WorkTimeProfile.objects.create(
            employment=self.employment,
            valid_from=date(2026, 1, 1),
            statutory_weekly_minutes=self.type_11.net_minutes() * 7,
            agreed_weekly_minutes=self.type_11.net_minutes() * 7,
            regime=WorkTimeProfile.Regime.CONTINUOUS,
            distribution=WorkTimeProfile.Distribution.UNEVEN,
        )
        matrix = build_month_matrix(user=self.staff, year=2026, month=9)
        row = next(r for r in matrix["rows"] if r["employee"].pk == self.employee.pk)
        self.assertTrue(row["fund"]["is_continuous"])
        # Září 2026 má 30 dnů; šablona každý den → fond days = 30
        self.assertEqual(row["fund"]["work_days"], 30)
        self.assertEqual(
            row["fund"]["daily_minutes"], self.type_11.net_minutes()
        )
        self.assertEqual(
            row["fund"]["fund_minutes"], 30 * self.type_11.net_minutes()
        )


class DynamicUvazekFondTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="dyn_fond",
            password="test-dyn",
            is_staff=True,
            is_superuser=True,
        )
        self.employee = Employee.objects.create(
            first_name="Dan",
            last_name="Dyn",
            internal_number="D001",
        )
        self.employment = Employment.objects.create(
            employee=self.employee,
            started_on=date(2026, 1, 1),
        )
        self.workplace = Workplace.objects.create(name="Dyn WP")
        EmployeeWorkplace.objects.create(
            employee=self.employee,
            workplace=self.workplace,
            valid_from=date(2026, 1, 1),
        )

    def test_mid_month_375_to_40_splits_fund(self):
        from apps.shifts.fund import fund_minutes_for_day, month_day_list
        from apps.shifts.holidays import holidays_for_year

        WorkTimeProfile.objects.create(
            employment=self.employment,
            valid_from=date(2026, 1, 1),
            valid_to=date(2026, 9, 15),
            statutory_weekly_minutes=2250,
            agreed_weekly_minutes=2250,
            regime=WorkTimeProfile.Regime.SINGLE,
        )
        WorkTimeProfile.objects.create(
            employment=self.employment,
            valid_from=date(2026, 9, 16),
            statutory_weekly_minutes=2400,
            agreed_weekly_minutes=2400,
            regime=WorkTimeProfile.Regime.SINGLE,
        )
        matrix = build_month_matrix(user=self.staff, year=2026, month=9)
        row = next(r for r in matrix["rows"] if r["employee"].pk == self.employee.pk)
        holiday_map = holidays_for_year(2026)
        expected = 0
        for day in month_day_list(2026, 9):
            expected += fund_minutes_for_day(
                self.employee, day, cells={}, holiday_map=holiday_map
            )
        self.assertEqual(row["fund"]["fund_minutes"], expected)
        self.assertNotEqual(expected, 22 * 8 * 60)
        self.assertIn("37", row["fund"]["segments_label"])
        self.assertIn("40", row["fund"]["segments_label"])

    def test_profile_overlap_rejected(self):
        WorkTimeProfile.objects.create(
            employment=self.employment,
            valid_from=date(2026, 1, 1),
            statutory_weekly_minutes=2400,
            agreed_weekly_minutes=2400,
        )
        form = WorkTimeProfileForm(
            data={
                "employment": self.employment.pk,
                "valid_from": "2026-06-01",
                "valid_to": "",
                "statutory_weekly_minutes": "2250",
                "agreed_weekly_minutes": "2250",
                "regime": WorkTimeProfile.Regime.SINGLE,
                "distribution": WorkTimeProfile.Distribution.EVEN,
                "is_active": "on",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors())

    def test_dynamic_balancing_target_and_summaries(self):
        profile = WorkTimeProfile.objects.create(
            employment=self.employment,
            valid_from=date(2026, 1, 1),
            statutory_weekly_minutes=2400,
            agreed_weekly_minutes=2400,
        )
        BalancingPeriod.objects.create(
            profile=profile,
            starts_on=date(2026, 9, 1),
            ends_on=date(2026, 9, 30),
            target_minutes=99999,
        )
        period = BalancingPeriod.objects.get(profile=profile)
        dyn = dynamic_balancing_target_minutes(period)
        self.assertEqual(dyn, 22 * 8 * 60)
        summary = fund_summary_for_employee(self.employee, date(2026, 9, 15))
        self.assertEqual(summary["target_minutes"], dyn)
        self.assertNotEqual(summary["target_minutes"], 99999)
        lists = balancing_summaries_for_month(self.employee, 2026, 9)
        self.assertEqual(len(lists), 1)
        self.assertEqual(lists[0]["target_minutes"], dyn)
