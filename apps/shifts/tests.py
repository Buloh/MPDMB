from datetime import date, datetime, time

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import ROLE_EMPLOYEE
from apps.employees.models import BalancingPeriod, Employee, Employment, WorkTimeProfile
from apps.shifts.forms import WorkTimeProfileForm
from apps.shifts.holidays import holidays_for_year
from apps.shifts.models import (
    EmployeeScheduleAssignment,
    ScheduleTemplate,
    ScheduleTemplateSlot,
    Shift,
    ShiftType,
)
from apps.shifts.services import (
    assign_shift_cell,
    build_month_matrix,
    calendar_month_fund,
    create_shift,
    employee_month_fund,
    employees_visible_for_shift_plan,
    format_workplace_segments_label,
    fund_summary_for_employee,
    generate_month_from_templates,
    generate_shifts_from_templates,
    monday_of_week,
    planned_net_minutes_for_employee_month,
    primary_workplace_for_month,
    resolve_daily_fund_minutes,
    workplace_segments_in_month,
)
from apps.workplaces.models import EmployeeWorkplace, Workplace


class MonthlyShiftPlanTests(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="Holub",
            password="22552255",
            is_staff=True,
            is_superuser=True,
        )
        self.worker_user = User.objects.create_user(
            username="petr",
            password="petr12345",
            is_staff=False,
        )
        Group.objects.get_or_create(name=ROLE_EMPLOYEE)
        self.worker_user.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        self.employee = Employee.objects.create(
            first_name="Petr",
            last_name="Svoboda",
            internal_number="S001",
            user=self.worker_user,
        )
        self.other = Employee.objects.create(
            first_name="Jana",
            last_name="Novakova",
            internal_number="S002",
        )
        self.workplace = Workplace.objects.create(
            name="Parkovaci dum Jih",
            address="Jizni 2",
        )
        EmployeeWorkplace.objects.create(
            employee=self.employee,
            workplace=self.workplace,
            valid_from=date(2026, 1, 1),
        )
        EmployeeWorkplace.objects.create(
            employee=self.other,
            workplace=self.workplace,
            valid_from=date(2026, 1, 1),
        )
        Employment.objects.create(
            employee=self.employee,
            started_on=date(2026, 1, 1),
            relation_type=Employment.RelationType.EMPLOYMENT,
            is_active=True,
        )
        Employment.objects.create(
            employee=self.other,
            started_on=date(2026, 1, 1),
            relation_type=Employment.RelationType.EMPLOYMENT,
            is_active=True,
        )
        self.type_r = ShiftType.objects.get(code="R")
        self.type_n = ShiftType.objects.get(code="N")
        self.tz = timezone.get_current_timezone()

    def _weekly_rrrrr(self, name="Ranny Po-Pa"):
        template = ScheduleTemplate.objects.create(
            name=name, cycle_length=7, is_active=True
        )
        template.ensure_slots()
        for i in range(5):
            ScheduleTemplateSlot.objects.filter(
                template=template, day_index=i
            ).update(shift_type=self.type_r)
        return template

    def test_night_type_crosses_midnight(self):
        self.assertTrue(self.type_n.crosses_midnight)
        self.assertEqual(self.type_n.net_minutes(), 8 * 60)
        start, end = self.type_n.bounds_for_date(date(2026, 10, 6))
        self.assertEqual(timezone.localtime(start).date(), date(2026, 10, 6))
        self.assertEqual(timezone.localtime(end).date(), date(2026, 10, 7))

    def test_month_matrix_role_filter(self):
        self.assertEqual(
            employees_visible_for_shift_plan(self.staff).count(), 2
        )
        self.assertEqual(
            list(
                employees_visible_for_shift_plan(self.worker_user).values_list(
                    "pk", flat=True
                )
            ),
            [self.employee.pk],
        )

    def test_assign_cell_and_planned_hours(self):
        shift = assign_shift_cell(
            user=self.staff,
            employee=self.employee,
            workplace=self.workplace,
            day=date(2026, 10, 6),
            shift_type=self.type_r,
            publish=True,
        )
        self.assertEqual(shift.status, Shift.Status.PUBLISHED)
        self.assertEqual(shift.shift_type_id, self.type_r.pk)
        minutes = planned_net_minutes_for_employee_month(
            self.employee, 2026, 10
        )
        self.assertEqual(minutes, 6 * 60)

        matrix = build_month_matrix(user=self.staff, year=2026, month=10)
        self.assertTrue(matrix["can_edit"])
        row = next(r for r in matrix["rows"] if r["employee"].pk == self.employee.pk)
        self.assertEqual(row["planned_minutes"], 6 * 60)
        cell = next(c for c in row["cells"] if c["day"].day == 6)
        self.assertEqual(cell["codes"], "R")
        self.assertEqual(cell["shifts"][0].display_code, "R")

    def test_overlap_rejected(self):
        assign_shift_cell(
            user=self.staff,
            employee=self.employee,
            workplace=self.workplace,
            day=date(2026, 10, 7),
            shift_type=self.type_r,
            publish=True,
        )
        from apps.shifts.services import ShiftConflictError

        # Same day same type replaces; different overlapping manual create
        shift = Shift(
            employee=self.employee,
            workplace=self.workplace,
            starts_at=timezone.make_aware(
                datetime(2026, 10, 7, 10, 0), self.tz
            ),
            ends_at=timezone.make_aware(
                datetime(2026, 10, 7, 18, 0), self.tz
            ),
        )
        with self.assertRaises(ShiftConflictError):
            create_shift(user=self.staff, shift=shift)

    def test_holiday_header(self):
        holidays = holidays_for_year(2026)
        self.assertIn(date(2026, 1, 1), holidays)
        self.assertIn(date(2026, 4, 3), holidays)  # Good Friday 2026
        matrix = build_month_matrix(user=self.staff, year=2026, month=1)
        jan1 = next(h for h in matrix["day_headers"] if h["day"].day == 1)
        self.assertTrue(jan1["is_holiday"])

    def test_weekday_labels_september_2026(self):
        matrix = build_month_matrix(user=self.staff, year=2026, month=9)
        by_day = {h["day"].day: h for h in matrix["day_headers"]}
        self.assertEqual(by_day[1]["weekday_label"], "Út")
        self.assertEqual(by_day[28]["weekday_label"], "Po")
        self.assertEqual(by_day[30]["weekday_label"], "St")
        self.client.login(username="Holub", password="22552255")
        response = self.client.get(
            reverse("shift_month"), {"year": 2026, "month": 9}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="muted day-dow"')
        self.assertContains(response, ">Út</span>")
        self.assertContains(response, ">Po</span>")

    def test_month_page_staff_and_employee(self):
        assign_shift_cell(
            user=self.staff,
            employee=self.employee,
            workplace=self.workplace,
            day=date(2026, 10, 8),
            shift_type=self.type_r,
            publish=True,
        )
        self.client.login(username="Holub", password="22552255")
        response = self.client.get(
            reverse("shift_month"), {"year": 2026, "month": 10}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Svoboda")
        self.assertContains(response, "Novakova")
        self.assertContains(response, ">R<")

        self.client.login(username="petr", password="petr12345")
        response = self.client.get(
            reverse("shift_month"), {"year": 2026, "month": 10}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Svoboda")
        self.assertNotContains(response, "Novakova")

    def test_shift_type_create_without_employee(self):
        self.client.login(username="Holub", password="22552255")
        response = self.client.post(
            reverse("shift_type_create"),
            {
                "code": "X",
                "name": "Zvláštní",
                "kind": "work",
                "start_time": "09:00",
                "end_time": "17:00",
                "break_minutes": 30,
                "counts_as_work": "on",
                "applies_on_holiday": "on",
                "is_active": "on",
                "sort_order": 50,
            },
        )
        self.assertEqual(response.status_code, 302)
        st = ShiftType.objects.get(code="X")
        self.assertEqual(st.name, "Zvláštní")
        self.assertEqual(st.kind, ShiftType.Kind.WORK)
        self.assertEqual(st.net_minutes(), 7 * 60 + 30)
        self.assertFalse(hasattr(st, "employee_id"))

        list_resp = self.client.get(reverse("shift_type_list"))
        self.assertEqual(list_resp.status_code, 200)
        self.assertContains(list_resp, "Zvláštní")

    def test_legacy_create_redirects_to_type(self):
        self.client.login(username="Holub", password="22552255")
        response = self.client.get(reverse("shift_create"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("shift_type_create"))

    def test_cell_assign_via_post(self):
        self.client.login(username="Holub", password="22552255")
        response = self.client.post(
            reverse("shift_cell_assign"),
            {
                "employee": self.employee.pk,
                "workplace": self.workplace.pk,
                "day": "2026-10-09",
                "shift_type": self.type_r.pk,
                "publish": "on",
                "year": 2026,
                "month": 10,
            },
        )
        self.assertEqual(response.status_code, 302)
        shift = Shift.objects.get(
            employee=self.employee,
            starts_at__date=date(2026, 10, 9),
        )
        self.assertEqual(shift.shift_type_id, self.type_r.pk)
        self.assertEqual(shift.status, Shift.Status.PUBLISHED)

    def test_generate_month_from_rrrrr_template(self):
        template = self._weekly_rrrrr()
        self.assertEqual(template.pattern_codes(), "RRRRR··")
        # Kotva = pondělí 28.09.2026, aby index 0 = Po
        EmployeeScheduleAssignment.objects.create(
            employee=self.employee,
            template=template,
            workplace=self.workplace,
            valid_from=date(2026, 10, 1),
            cycle_anchor_date=date(2026, 9, 28),
        )
        assign_shift_cell(
            user=self.staff,
            employee=self.employee,
            workplace=self.workplace,
            day=date(2026, 10, 6),
            shift_type=self.type_n,
            publish=True,
        )
        result = generate_month_from_templates(
            user=self.staff,
            year=2026,
            month=10,
            template=template,
            workplace=self.workplace,
            cycle_anchor_date=date(2026, 9, 28),
            employee_ids=[self.employee.pk],
        )
        self.assertGreater(result["created"], 0)

        kept = Shift.objects.get(
            employee=self.employee,
            starts_at__date=date(2026, 10, 6),
            shift_type=self.type_n,
        )
        self.assertEqual(kept.shift_type_id, self.type_n.pk)
        # Šablona přidá i R (nepřekrývá se s N)
        self.assertTrue(
            Shift.objects.filter(
                employee=self.employee,
                starts_at__date=date(2026, 10, 6),
                shift_type=self.type_r,
            ).exists()
        )

        mon = Shift.objects.get(
            employee=self.employee,
            starts_at__date=date(2026, 10, 5),
        )
        self.assertEqual(mon.shift_type_id, self.type_r.pk)
        self.assertFalse(
            Shift.objects.filter(
                employee=self.employee,
                starts_at__date=date(2026, 10, 10),
            ).exists()
        )
        self.assertFalse(
            Shift.objects.filter(
                employee=self.employee,
                starts_at__date=date(2026, 10, 11),
            ).exists()
        )

    def test_cell_prefill_from_template(self):
        template = self._weekly_rrrrr("Ranny")
        EmployeeScheduleAssignment.objects.create(
            employee=self.employee,
            template=template,
            workplace=self.workplace,
            valid_from=date(2026, 1, 1),
            cycle_anchor_date=date(2026, 9, 28),
        )
        self.client.login(username="Holub", password="22552255")
        response = self.client.get(
            reverse("shift_cell_assign"),
            {
                "year": 2026,
                "month": 10,
                "employee": self.employee.pk,
                "day": "2026-10-07",
            },
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("shift_type"), self.type_r.pk)
        self.assertEqual(form.initial.get("workplace"), self.workplace.pk)

    def test_14day_cycle_and_balancing_fund(self):
        template = ScheduleTemplate.objects.create(
            name="Kratky dlouhy", cycle_length=14
        )
        template.ensure_slots()
        for i in range(5):
            ScheduleTemplateSlot.objects.filter(
                template=template, day_index=i
            ).update(shift_type=self.type_r)
        # week 2 remains empty
        self.assertEqual(template.pattern_codes(), "RRRRR·········")
        EmployeeScheduleAssignment.objects.create(
            employee=self.employee,
            template=template,
            workplace=self.workplace,
            valid_from=date(2026, 10, 1),
            cycle_anchor_date=date(2026, 9, 28),
        )
        employment = Employment.objects.filter(employee=self.employee).first()
        if employment is None:
            employment = Employment.objects.create(
                employee=self.employee,
                started_on=date(2026, 1, 1),
                relation_type=Employment.RelationType.EMPLOYMENT,
            )
        profile = WorkTimeProfile.objects.create(
            employment=employment,
            valid_from=date(2026, 1, 1),
            statutory_weekly_minutes=40 * 60,
            agreed_weekly_minutes=40 * 60,
            regime=WorkTimeProfile.Regime.CONTINUOUS,
            distribution=WorkTimeProfile.Distribution.UNEVEN,
        )
        period = BalancingPeriod.objects.create(
            profile=profile,
            starts_on=date(2026, 10, 1),
            ends_on=date(2026, 11, 15),
            target_minutes=BalancingPeriod.compute_target_minutes(
                40 * 60, date(2026, 10, 1), date(2026, 11, 15)
            ),
        )
        result = generate_month_from_templates(
            user=self.staff,
            year=2026,
            month=10,
            template=template,
            workplace=self.workplace,
            cycle_anchor_date=date(2026, 9, 28),
            employee_ids=[self.employee.pk],
        )
        self.assertGreater(result["created"], 0)
        # Horizont období přesahuje říjen – generuj explicitně od–do
        result2 = generate_shifts_from_templates(
            user=self.staff,
            date_from=date(2026, 11, 1),
            date_to=date(2026, 11, 15),
            template=template,
            workplace=self.workplace,
            cycle_anchor_date=date(2026, 9, 28),
            employee_ids=[self.employee.pk],
        )
        self.assertGreaterEqual(result2["created"], 0)
        self.assertTrue(
            Shift.objects.filter(
                employee=self.employee,
                starts_at__date=date(2026, 11, 9),
            ).exists()
            or result2["skipped_empty"] > 0
            or result2["created"] > 0
        )
        # Po 9.11.2026 je v 14denním cyklu den index 0 (R)
        gen_nov = generate_shifts_from_templates(
            user=self.staff,
            date_from=date(2026, 11, 9),
            date_to=date(2026, 11, 9),
            template=template,
            workplace=self.workplace,
            cycle_anchor_date=date(2026, 9, 28),
            employee_ids=[self.employee.pk],
        )
        self.assertTrue(
            Shift.objects.filter(
                employee=self.employee,
                starts_at__date=date(2026, 11, 9),
                shift_type=self.type_r,
            ).exists()
        )
        matrix = build_month_matrix(user=self.staff, year=2026, month=10)
        row = next(r for r in matrix["rows"] if r["employee"].pk == self.employee.pk)
        self.assertIsNotNone(row["fund"])
        self.assertEqual(row["fund"]["daily_minutes"], 8 * 60)
        self.assertTrue(row["fund"]["is_continuous"])
        self.assertGreater(row["fund"]["work_days"], 0)
        self.assertEqual(
            row["fund"]["fund_minutes"],
            row["fund"]["work_days"] * 8 * 60,
        )
        balancing = fund_summary_for_employee(self.employee, date(2026, 10, 15))
        self.assertIsNotNone(balancing)
        from apps.shifts.fund import dynamic_balancing_target_minutes

        self.assertEqual(
            balancing["target_minutes"],
            dynamic_balancing_target_minutes(period),
        )
        self.assertEqual(self.type_r.net_hours_label, "6:00")

    def test_two_non_overlapping_shifts_same_day(self):
        assign_shift_cell(
            user=self.staff,
            employee=self.employee,
            workplace=self.workplace,
            day=date(2026, 10, 6),
            shift_type=self.type_r,
            publish=True,
        )
        night = assign_shift_cell(
            user=self.staff,
            employee=self.employee,
            workplace=self.workplace,
            day=date(2026, 10, 6),
            shift_type=self.type_n,
            publish=True,
        )
        self.assertEqual(night.shift_type_id, self.type_n.pk)
        matrix = build_month_matrix(user=self.staff, year=2026, month=10)
        row = next(r for r in matrix["rows"] if r["employee"].pk == self.employee.pk)
        cell = next(c for c in row["cells"] if c["day"].day == 6)
        self.assertEqual(len(cell["shifts"]), 2)
        self.assertIn("R", cell["codes"])
        self.assertIn("N", cell["codes"])

    def test_generate_dialog_page(self):
        template = self._weekly_rrrrr()
        self.client.login(username="Holub", password="22552255")
        response = self.client.get(
            reverse("shift_generate_month"), {"year": 2026, "month": 10}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Celý rok")
        self.assertContains(response, "Šablona")
        self.assertContains(response, self.employee.last_name)
        post = self.client.post(
            reverse("shift_generate_month"),
            {
                "range_mode": "month",
                "year": 2026,
                "month": 10,
                "template": template.pk,
                "workplace": self.workplace.pk,
                "cycle_anchor_date": "2026-09-28",
                "employees": [self.employee.pk],
            },
        )
        self.assertEqual(post.status_code, 302)
        self.assertTrue(
            Shift.objects.filter(
                employee=self.employee, shift_type=self.type_r
            ).exists()
        )

    def test_generate_hides_employee_before_employment(self):
        Employment.objects.filter(employee=self.employee).delete()
        Employment.objects.create(
            employee=self.employee,
            started_on=date(2026, 11, 1),
            relation_type=Employment.RelationType.EMPLOYMENT,
            is_active=True,
        )
        self.client.login(username="Holub", password="22552255")
        response = self.client.get(
            reverse("shift_generate_month"), {"year": 2026, "month": 9}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.employee.last_name)
        self.assertNotContains(response, self.employee.first_name)

        nov = self.client.get(
            reverse("shift_generate_month"), {"year": 2026, "month": 11}
        )
        self.assertEqual(nov.status_code, 200)
        self.assertContains(nov, self.employee.last_name)

    def test_generate_without_assignment_uses_form_template(self):
        template = self._weekly_rrrrr("Bez prirazeni")
        self.assertFalse(
            EmployeeScheduleAssignment.objects.filter(employee=self.employee).exists()
        )
        result = generate_shifts_from_templates(
            user=self.staff,
            date_from=date(2026, 10, 5),
            date_to=date(2026, 10, 9),
            template=template,
            workplace=self.workplace,
            cycle_anchor_date=date(2026, 9, 28),
            employee_ids=[self.employee.pk],
        )
        self.assertGreater(result["created"], 0)
        self.assertTrue(
            Shift.objects.filter(
                employee=self.employee,
                starts_at__date=date(2026, 10, 5),
                shift_type=self.type_r,
            ).exists()
        )

    def test_cell_modal_partial_and_workplace_fallback(self):
        self.client.login(username="Holub", password="22552255")
        get_resp = self.client.get(
            reverse("shift_cell_modal"),
            {
                "year": 2026,
                "month": 10,
                "employee": self.employee.pk,
                "day": "2026-10-07",
                "partial": "1",
            },
        )
        self.assertEqual(get_resp.status_code, 200)
        self.assertContains(get_resp, "Přidat směnu")
        self.assertNotContains(get_resp, "<html")
        post = self.client.post(
            reverse("shift_cell_modal"),
            {
                "partial": "1",
                "year": 2026,
                "month": 10,
                "employee": self.employee.pk,
                "day": "2026-10-07",
                "shift_type": self.type_r.pk,
                "publish": "on",
            },
        )
        self.assertEqual(post.status_code, 200)
        self.assertEqual(post.json()["ok"], True)
        self.assertTrue(
            Shift.objects.filter(
                employee=self.employee,
                starts_at__date=date(2026, 10, 7),
                shift_type=self.type_r,
            ).exists()
        )

    def test_monday_anchor_fills_mondays_in_september(self):
        template = self._weekly_rrrrr("Po-Pa zari")
        # 1.9.2026 = Út; kotva musí být Po 31.8., jinak pondělí vypadnou
        self.assertEqual(monday_of_week(date(2026, 9, 1)), date(2026, 8, 31))
        result = generate_shifts_from_templates(
            user=self.staff,
            date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 30),
            template=template,
            workplace=self.workplace,
            cycle_anchor_date=monday_of_week(date(2026, 9, 1)),
            employee_ids=[self.employee.pk],
        )
        self.assertGreater(result["created"], 0)
        for day in (7, 14, 21):
            self.assertTrue(
                Shift.objects.filter(
                    employee=self.employee,
                    starts_at__date=date(2026, 9, day),
                    shift_type=self.type_r,
                ).exists(),
                msg=f"Očekávána směna R dne {day}.9.2026",
            )

    def test_holiday_respects_applies_on_holiday(self):
        template = self._weekly_rrrrr("Svatky")
        # 28.9.2026 = Po + státní svátek
        self.type_r.applies_on_holiday = True
        self.type_r.save(update_fields=["applies_on_holiday"])
        generate_shifts_from_templates(
            user=self.staff,
            date_from=date(2026, 9, 28),
            date_to=date(2026, 9, 28),
            template=template,
            workplace=self.workplace,
            cycle_anchor_date=date(2026, 9, 28),
            employee_ids=[self.employee.pk],
        )
        self.assertTrue(
            Shift.objects.filter(
                employee=self.employee,
                starts_at__date=date(2026, 9, 28),
                shift_type=self.type_r,
            ).exists()
        )
        Shift.objects.filter(employee=self.employee).delete()
        self.type_r.applies_on_holiday = False
        self.type_r.save(update_fields=["applies_on_holiday"])
        result = generate_shifts_from_templates(
            user=self.staff,
            date_from=date(2026, 9, 28),
            date_to=date(2026, 9, 28),
            template=template,
            workplace=self.workplace,
            cycle_anchor_date=date(2026, 9, 28),
            employee_ids=[self.employee.pk],
        )
        self.assertEqual(result["skipped_holiday"], 1)
        self.assertFalse(
            Shift.objects.filter(
                employee=self.employee,
                starts_at__date=date(2026, 9, 28),
            ).exists()
        )
        self.type_r.applies_on_holiday = True
        self.type_r.save(update_fields=["applies_on_holiday"])

    def test_month_page_has_context_menu_markup(self):
        self.client.login(username="Holub", password="22552255")
        response = self.client.get(
            reverse("shift_month"), {"year": 2026, "month": 9}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "shift-cell-menu")
        self.assertContains(response, "cell_menu.js")
        self.assertContains(response, 'data-employee=')

    def test_matrix_fund_delta_planned_vs_calendar(self):
        assign_shift_cell(
            user=self.staff,
            employee=self.employee,
            workplace=self.workplace,
            day=date(2026, 9, 1),
            shift_type=self.type_r,
            publish=True,
        )
        matrix = build_month_matrix(user=self.staff, year=2026, month=9)
        row = next(r for r in matrix["rows"] if r["employee"].pk == self.employee.pk)
        # Bez úvazku: denní fond z dominantního typu směny (R)
        daily = self.type_r.net_minutes()
        self.assertEqual(row["fund"]["daily_minutes"], daily)
        self.assertEqual(row["fund"]["fund_minutes"], 22 * daily)
        self.assertEqual(row["planned_minutes"], daily)
        self.assertTrue(row["fund_delta_short"])
        self.assertEqual(
            row["fund_delta_minutes"],
            row["planned_minutes"] - row["fund"]["fund_minutes"],
        )

    def test_workplace_group_uses_month_overlap(self):
        EmployeeWorkplace.objects.filter(employee=self.employee).delete()
        EmployeeWorkplace.objects.create(
            employee=self.employee,
            workplace=self.workplace,
            valid_from=date(2026, 9, 20),
        )
        matrix = build_month_matrix(user=self.staff, year=2026, month=9)
        row = next(r for r in matrix["rows"] if r["employee"].pk == self.employee.pk)
        self.assertEqual(row["workplace_name"], self.workplace.name)
        self.assertIn(self.workplace.name, row["workplace_segments_label"])
        self.assertIn("od 20.09.2026", row["workplace_segments_label"])

    def test_workplace_only_hidden_without_employment(self):
        """Samotné pracoviště bez vztahu nestačí — řádek v plánu není."""
        Employment.objects.filter(employee=self.employee).delete()
        EmployeeWorkplace.objects.filter(employee=self.employee).delete()
        EmployeeWorkplace.objects.create(
            employee=self.employee,
            workplace=self.workplace,
            valid_from=date(2026, 10, 1),
        )
        matrix_sep = build_month_matrix(user=self.staff, year=2026, month=9)
        sep_ids = [r["employee"].pk for r in matrix_sep["rows"]]
        self.assertNotIn(self.employee.pk, sep_ids)

        matrix_oct = build_month_matrix(user=self.staff, year=2026, month=10)
        oct_ids = [r["employee"].pk for r in matrix_oct["rows"]]
        self.assertNotIn(self.employee.pk, oct_ids)

    def test_assign_before_employment_start_rejected(self):
        Employment.objects.filter(employee=self.employee).delete()
        Employment.objects.create(
            employee=self.employee,
            started_on=date(2026, 11, 1),
            relation_type=Employment.RelationType.EMPLOYMENT,
            is_active=True,
        )
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError) as ctx:
            assign_shift_cell(
                user=self.staff,
                employee=self.employee,
                workplace=self.workplace,
                day=date(2026, 10, 5),
                shift_type=self.type_r,
                publish=True,
            )
        self.assertIn("pracovní vztah", str(ctx.exception))

        matrix = build_month_matrix(user=self.staff, year=2026, month=10)
        self.assertNotIn(
            self.employee.pk, [r["employee"].pk for r in matrix["rows"]]
        )

        shift = assign_shift_cell(
            user=self.staff,
            employee=self.employee,
            workplace=self.workplace,
            day=date(2026, 11, 2),
            shift_type=self.type_r,
            publish=True,
        )
        self.assertEqual(shift.status, Shift.Status.PUBLISHED)

    def test_generate_skips_days_without_employment(self):
        Employment.objects.filter(employee=self.employee).delete()
        Employment.objects.create(
            employee=self.employee,
            started_on=date(2026, 10, 15),
            relation_type=Employment.RelationType.EMPLOYMENT,
            is_active=True,
        )
        template = self._weekly_rrrrr()
        result = generate_shifts_from_templates(
            user=self.staff,
            date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 31),
            template=template,
            workplace=self.workplace,
            cycle_anchor_date=monday_of_week(date(2026, 10, 1)),
            employee_ids=[self.employee.pk],
        )
        self.assertGreater(result["skipped_no_employment"], 0)
        self.assertGreater(result["created"], 0)
        early = 0
        for s in Shift.objects.filter(employee=self.employee):
            if timezone.localtime(s.starts_at).date() < date(2026, 10, 15):
                early += 1
        self.assertEqual(early, 0)

    def test_employed_without_workplace_shown_in_month(self):
        EmployeeWorkplace.objects.filter(employee=self.employee).delete()
        EmployeeWorkplace.objects.create(
            employee=self.employee,
            workplace=self.workplace,
            valid_from=date(2026, 10, 1),
        )
        matrix = build_month_matrix(user=self.staff, year=2026, month=9)
        row = next(r for r in matrix["rows"] if r["employee"].pk == self.employee.pk)
        self.assertEqual(row["workplace_name"], "Bez pracoviště")
        self.assertIn("od 01.10.2026", row["workplace_future_hint"])
        self.assertIn(self.workplace.name, row["workplace_future_hint"])

    def test_ended_employment_without_workplace_hidden(self):
        EmployeeWorkplace.objects.filter(employee=self.employee).delete()
        Employment.objects.filter(employee=self.employee).delete()
        Employment.objects.create(
            employee=self.employee,
            started_on=date(2025, 1, 1),
            ended_on=date(2026, 8, 31),
            relation_type=Employment.RelationType.EMPLOYMENT,
        )
        matrix = build_month_matrix(user=self.staff, year=2026, month=9)
        sep_ids = [r["employee"].pk for r in matrix["rows"]]
        self.assertNotIn(self.employee.pk, sep_ids)

    def test_mid_month_workplace_segments(self):
        other_wp = Workplace.objects.create(name="Parkovaci dum Sever")
        EmployeeWorkplace.objects.filter(employee=self.employee).delete()
        EmployeeWorkplace.objects.create(
            employee=self.employee,
            workplace=self.workplace,
            valid_from=date(2026, 9, 1),
            valid_to=date(2026, 9, 15),
        )
        EmployeeWorkplace.objects.create(
            employee=self.employee,
            workplace=other_wp,
            valid_from=date(2026, 9, 16),
        )
        month_start, month_end = date(2026, 9, 1), date(2026, 9, 30)
        segments = workplace_segments_in_month(
            self.employee, month_start, month_end
        )
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["workplace"], self.workplace)
        self.assertEqual(segments[0]["ends_on"], date(2026, 9, 15))
        self.assertEqual(segments[1]["workplace"], other_wp)
        self.assertEqual(segments[1]["starts_on"], date(2026, 9, 16))
        # Střed září = 15. → ještě první pracoviště
        primary = primary_workplace_for_month(
            self.employee, month_start, month_end
        )
        self.assertEqual(primary, self.workplace)
        label = format_workplace_segments_label(segments)
        self.assertIn(self.workplace.name, label)
        self.assertIn(other_wp.name, label)
        matrix = build_month_matrix(user=self.staff, year=2026, month=9)
        row = next(r for r in matrix["rows"] if r["employee"].pk == self.employee.pk)
        self.assertEqual(row["workplace_name"], self.workplace.name)
        self.assertIn(other_wp.name, row["workplace_segments_label"])
        self.assertIn("01.09.2026–15.09.2026", row["workplace_segments_label"])
        self.assertIn("od 16.09.2026", row["workplace_segments_label"])

    def test_single_workplace_month_shows_od_do_label(self):
        matrix = build_month_matrix(user=self.staff, year=2026, month=10)
        row = next(r for r in matrix["rows"] if r["employee"].pk == self.employee.pk)
        self.assertEqual(row["workplace_name"], self.workplace.name)
        self.assertIn(self.workplace.name, row["workplace_segments_label"])
        self.assertIn("od 01.01.2026", row["workplace_segments_label"])

    def test_calendar_month_fund_september_2026(self):
        fund = calendar_month_fund(2026, 9, daily_minutes=8 * 60)
        self.assertEqual(fund["work_days"], 22)
        self.assertEqual(fund["holiday_weekdays"], 1)
        self.assertEqual(fund["fund_minutes"], 22 * 8 * 60)
        self.assertEqual(fund["fund_label"], "176")
        # Všední svátek se do fondu počítá: 21+1 = 22 dnů × 8 h
        self.assertEqual(fund["holiday_minutes"], 8 * 60)

    def test_standby_not_in_planned_minutes(self):
        standby = ShiftType.objects.create(
            code="P",
            name="Pohotovost",
            kind=ShiftType.Kind.STANDBY,
            start_time=time(14, 0),
            end_time=time(22, 0),
            break_minutes=0,
            counts_as_work=True,
            sort_order=90,
        )
        assign_shift_cell(
            user=self.staff,
            employee=self.employee,
            workplace=self.workplace,
            day=date(2026, 10, 5),
            shift_type=self.type_r,
            publish=True,
        )
        assign_shift_cell(
            user=self.staff,
            employee=self.employee,
            workplace=self.workplace,
            day=date(2026, 10, 5),
            shift_type=standby,
            publish=True,
        )
        matrix = build_month_matrix(user=self.staff, year=2026, month=10)
        row = next(r for r in matrix["rows"] if r["employee"].pk == self.employee.pk)
        self.assertEqual(row["planned_minutes"], self.type_r.net_minutes())
        cell = next(c for c in row["cells"] if c["day"].day == 5)
        self.assertIn("(P)", cell["codes"])
