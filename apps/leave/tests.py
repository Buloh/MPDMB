"""Testy hubu Provoz a roční dovolené."""

from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.attendance.models import WorkInterval
from apps.employees.models import Employee, Employment, WorkTimeProfile
from apps.shifts.models import Shift, ShiftType
from apps.workplaces.models import EmployeeWorkplace, Workplace

from .entitlement import compute_entitlement_breakdown
from .models import (
    EmployeeLeaveSettings,
    LeaveEntitlement,
    LeavePlan,
    LeavePlanDay,
    LeavePolicySettings,
)
from .services import (
    LeaveConflictError,
    continuous_working_days,
    create_leave_plan,
    ensure_entitlement,
    format_leave_balance,
)


class OpsHubTests(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="leave_admin",
            password="adminpass1",
            is_staff=True,
            is_superuser=True,
        )

    def test_home_has_ops_not_separate_shifts(self):
        self.client.login(username="leave_admin", password="adminpass1")
        home = self.client.get(reverse("home"))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "Provoz")
        self.assertContains(home, reverse("ops_hub"))
        hub = self.client.get(reverse("ops_hub"))
        self.assertEqual(hub.status_code, 200)
        self.assertContains(hub, "Dlouhodobý plán")
        self.assertContains(hub, "Docházka")
        self.assertContains(hub, "Dovolená")
        self.assertContains(hub, reverse("leave_year"))


class LeaveModuleTests(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="leave_mgr",
            password="adminpass1",
            is_staff=True,
            is_superuser=True,
        )
        self.employee = Employee.objects.create(
            first_name="Eva",
            last_name="Dovolena",
            internal_number="LV001",
        )
        self.workplace = Workplace.objects.create(
            name="Park Dovolena",
            address="Test 3",
        )
        EmployeeWorkplace.objects.create(
            employee=self.employee,
            workplace=self.workplace,
            valid_from=date(2026, 1, 1),
        )
        self.employment = Employment.objects.create(
            employee=self.employee,
            started_on=date(2026, 1, 1),
            is_active=True,
            relation_type=Employment.RelationType.EMPLOYMENT,
            pay_regime=Employment.PayRegime.WAGE,
        )
        WorkTimeProfile.objects.create(
            employment=self.employment,
            valid_from=date(2026, 1, 1),
            statutory_weekly_minutes=2400,
            agreed_weekly_minutes=2400,
            is_active=True,
        )
        LeavePolicySettings.load()
        self.tz = timezone.get_current_timezone()

    def _add_confirmed_work_multiples(self, multiples: int, *, start: date | None = None):
        """Přidá potvrzený WorkInterval o n násobcích týdenní doby."""
        weekly = 2400
        day = start or date(2026, 1, 5)
        type_r = ShiftType.objects.get(code="R")
        starts = timezone.make_aware(datetime.combine(day, time(6, 0)), self.tz)
        ends = starts + timedelta(minutes=weekly * multiples + 60)
        shift = Shift.objects.create(
            employee=self.employee,
            workplace=self.workplace,
            shift_type=type_r,
            starts_at=starts,
            ends_at=ends,
            status=Shift.Status.PUBLISHED,
        )
        WorkInterval.objects.create(
            employment=self.employment,
            workplace=self.workplace,
            shift=shift,
            starts_at=starts,
            ends_at=ends,
            break_minutes=0,
            status=WorkInterval.Status.CONFIRMED,
        )

    def test_entitlement_zero_without_work(self):
        ent = ensure_entitlement(self.employment, 2026)
        self.assertIsNotNone(ent)
        self.assertEqual(ent.accrued_minutes, 0)
        self.assertEqual(ent.entitled_minutes, 0)
        self.assertIsNone(ent.must_use_by)

    def test_entitlement_november_start_no_work(self):
        self.employment.started_on = date(2026, 11, 1)
        self.employment.save(update_fields=["started_on"])
        ent = ensure_entitlement(self.employment, 2026)
        self.assertEqual(ent.accrued_minutes, 0)
        self.assertEqual(ent.entitled_minutes, 0)
        self.assertIsNone(ensure_entitlement(self.employment, 2025))

    def test_entitlement_four_multiples_accrues(self):
        self._add_confirmed_work_multiples(4)
        b = compute_entitlement_breakdown(
            self.employment, 2026, today=date(2026, 12, 31)
        )
        self.assertEqual(b.accrued_multiples, 4)
        self.assertGreater(b.accrued_minutes, 0)
        # 4/52 * 2400 * 4 = 738.46 → ceil na 13 h = 780 min
        self.assertEqual(b.accrued_minutes, 780)
        ent = ensure_entitlement(self.employment, 2026)
        self.assertEqual(ent.accrued_minutes, 780)

    def test_entitlement_full_year_fifty_two_multiples(self):
        self._add_confirmed_work_multiples(52)
        ent = ensure_entitlement(self.employment, 2026)
        self.assertEqual(ent.accrued_minutes, 9600)
        self.assertEqual(ent.entitled_minutes, 9600)
        self.assertEqual(ent.remaining_minutes, 9600)
        self.assertIsNone(ent.must_use_by)

    def test_must_use_by_only_with_carryover_end_of_year(self):
        """§ 218 odst. 3: převod z Y-1 vyčerpat do 31.12.Y (ne Y+1)."""
        ent = ensure_entitlement(self.employment, 2026)
        self.assertIsNotNone(ent)
        self.assertEqual(ent.carried_in_minutes, 0)
        self.assertIsNone(ent.must_use_by)

        ent.carried_in_minutes = 480
        ent.save(update_fields=["carried_in_minutes"])
        ent = ensure_entitlement(self.employment, 2026)
        self.assertEqual(ent.must_use_by, date(2026, 12, 31))

        ent.carried_in_minutes = 0
        ent.save(update_fields=["carried_in_minutes"])
        ent = ensure_entitlement(self.employment, 2026)
        self.assertIsNone(ent.must_use_by)

    def test_own_leave_deadlines_and_warn_flags(self):
        """Nárok roku: ideálně 31.12.Y, nejzazší 31.12.Y+1; varování ze zůstatku."""
        from apps.leave.services import own_leave_warn_flags

        self._add_confirmed_work_multiples(52)
        ent = ensure_entitlement(self.employment, 2026)
        self.assertEqual(ent.preferred_use_by, date(2026, 12, 31))
        self.assertEqual(ent.statutory_latest_use_by, date(2027, 12, 31))
        self.assertFalse(ent.deadlines_manual)
        self.assertGreater(ent.own_year_remaining_minutes, 0)

        mid_year = own_leave_warn_flags(ent, today=date(2026, 6, 15))
        self.assertFalse(mid_year["warn_own_year"])
        self.assertFalse(mid_year["warn_own_deadline"])

        after_year = own_leave_warn_flags(ent, today=date(2027, 1, 2))
        self.assertTrue(after_year["warn_own_year"])
        self.assertFalse(after_year["warn_own_deadline"])

        near_latest = own_leave_warn_flags(ent, today=date(2027, 10, 15))
        self.assertTrue(near_latest["warn_own_year"])
        self.assertTrue(near_latest["warn_own_deadline"])

        empty = LeaveEntitlement(
            employment=self.employment,
            year=2025,
            entitled_minutes=0,
            accrued_minutes=0,
        )
        self.assertIsNone(empty.default_statutory_latest_use_by())

    def test_manual_deadlines_not_overwritten(self):
        self._add_confirmed_work_multiples(52)
        ent = ensure_entitlement(self.employment, 2026)
        custom = date(2028, 6, 30)
        ent.statutory_latest_use_by = custom
        ent.preferred_use_by = date(2026, 11, 30)
        ent.deadlines_manual = True
        ent.save()
        ent = ensure_entitlement(self.employment, 2026)
        self.assertEqual(ent.statutory_latest_use_by, custom)
        self.assertEqual(ent.preferred_use_by, date(2026, 11, 30))
        self.assertTrue(ent.deadlines_manual)

    def test_approve_creates_leave_shifts(self):
        self._add_confirmed_work_multiples(52)
        plan = create_leave_plan(
            user=self.staff,
            employment=self.employment,
            year=2026,
            starts_on=date(2026, 7, 6),
            ends_on=date(2026, 7, 10),
            approve=True,
        )
        self.assertEqual(plan.status, LeavePlan.Status.APPROVED)
        self.assertTrue(plan.days.exists())
        st = ShiftType.objects.get(code="D")
        self.assertEqual(st.kind, ShiftType.Kind.LEAVE)
        shifts = Shift.objects.filter(
            employee=self.employee, shift_type=st, status=Shift.Status.PUBLISHED
        )
        self.assertEqual(shifts.count(), plan.days.count())
        ent = LeaveEntitlement.objects.get(employment=self.employment, year=2026)
        self.assertEqual(ent.planned_minutes, plan.total_minutes)
        self.assertLess(ent.remaining_minutes, ent.entitled_minutes)

    def test_overlap_with_work_shift_blocked(self):
        type_r = ShiftType.objects.get(code="R")
        day = date(2026, 8, 3)
        start = timezone.make_aware(datetime.combine(day, type_r.start_time), self.tz)
        end = timezone.make_aware(datetime.combine(day, type_r.end_time), self.tz)
        Shift.objects.create(
            employee=self.employee,
            workplace=self.workplace,
            shift_type=type_r,
            starts_at=start,
            ends_at=end,
            status=Shift.Status.PUBLISHED,
        )
        from .services import LeaveConflictError

        with self.assertRaises(LeaveConflictError):
            create_leave_plan(
                user=self.staff,
                employment=self.employment,
                year=2026,
                starts_on=day,
                ends_on=day,
                approve=True,
            )

    def test_year_page_ok(self):
        self.client.login(username="leave_mgr", password="adminpass1")
        response = self.client.get(reverse("leave_year") + "?year=2026")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dovolena")
        self.assertContains(response, "0,0 d")
        self.assertContains(response, "Naběhlé")
        self.assertContains(response, "Park Dovolena")
        self.assertContains(response, "leave-year-table")
        self.assertNotContains(response, ">Detail</a>")
        detail_url = (
            reverse("leave_employee", args=[self.employee.pk]) + "?year=2026"
        )
        self.assertContains(response, detail_url)
        self.assertContains(response, "Dovolena Eva")
        detail = self.client.get(detail_url)
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Kalendář 2026")
        self.assertContains(detail, "Přidat blok")
        self.assertContains(detail, "leave-year-grid")
        self.assertContains(detail, "leave-month-days")
        self.assertContains(detail, "Naběhlé")

    def test_workplace_year_calendar(self):
        self.client.login(username="leave_mgr", password="adminpass1")
        response = self.client.get(
            reverse("leave_workplace", args=[self.workplace.pk]) + "?year=2026"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dovolena")
        self.assertContains(response, "leave-year-grid")
        self.assertContains(response, "Přidat blok")

    def test_modal_create_plan_json(self):
        self._add_confirmed_work_multiples(52)
        self.client.login(username="leave_mgr", password="adminpass1")
        partial = self.client.get(
            reverse("leave_plan_form_partial"),
            {
                "employee_id": self.employee.pk,
                "year": 2026,
                "starts_on": "2026-07-06",
            },
        )
        self.assertEqual(partial.status_code, 200)
        self.assertContains(partial, "Blok dovolené")
        self.assertContains(partial, 'value="2026-07-06"')
        self.assertRegex(
            partial.content.decode(),
            r'name="ends_on"[^>]*value=""|name="ends_on"(?![^>]*value=)',
        )
        response = self.client.post(
            reverse("leave_plan_create"),
            {
                "employee_id": self.employee.pk,
                "year": "2026",
                "starts_on": "2026-07-06",
                "ends_on": "",
                "portion": "full",
                "note": "",
                "approve_now": "on",
            },
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        plan = LeavePlan.objects.get(
            employment=self.employment, year=2026, status=LeavePlan.Status.APPROVED
        )
        self.assertEqual(plan.starts_on, date(2026, 7, 6))
        self.assertEqual(plan.ends_on, date(2026, 7, 6))

        multi = self.client.post(
            reverse("leave_plan_create"),
            {
                "employee_id": self.employee.pk,
                "year": "2026",
                "starts_on": "2026-08-03",
                "ends_on": "2026-08-05",
                "portion": "full",
                "note": "",
                "approve_now": "on",
            },
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(multi.status_code, 200)
        self.assertTrue(multi.json()["ok"])

    def test_format_leave_balance_days_and_hours(self):
        label = format_leave_balance(9600, 480)
        self.assertEqual(label, "20,0 d (160)")
        half = format_leave_balance(240, 480)
        self.assertEqual(half, "0,5 d (4)")

    def test_half_day_creates_half_minutes_shift(self):
        self._add_confirmed_work_multiples(52)
        day = date(2026, 7, 6)
        plan = create_leave_plan(
            user=self.staff,
            employment=self.employment,
            year=2026,
            starts_on=day,
            ends_on=day,
            portion=LeavePlanDay.Portion.AM,
            approve=True,
        )
        self.assertEqual(plan.status, LeavePlan.Status.APPROVED)
        self.assertEqual(plan.total_minutes, 240)
        day_row = plan.days.get()
        self.assertEqual(day_row.portion, LeavePlanDay.Portion.AM)
        self.assertEqual(day_row.minutes, 240)
        shift = day_row.shift
        self.assertIsNotNone(shift)
        self.assertEqual(shift.planned_net_minutes(), 240)
        self.assertEqual(shift.display_code, "D/")

    def test_half_day_blocked_when_disabled(self):
        self._add_confirmed_work_multiples(52)
        policy = LeavePolicySettings.load()
        policy.allow_half_day = False
        policy.save()
        with self.assertRaises(LeaveConflictError):
            create_leave_plan(
                user=self.staff,
                employment=self.employment,
                year=2026,
                starts_on=date(2026, 7, 6),
                ends_on=date(2026, 7, 6),
                portion=LeavePlanDay.Portion.PM,
                approve=True,
            )

    def test_employee_override_blocks_half_day(self):
        self._add_confirmed_work_multiples(52)
        EmployeeLeaveSettings.objects.create(
            employment=self.employment,
            allow_half_day=False,
        )
        with self.assertRaises(LeaveConflictError):
            create_leave_plan(
                user=self.staff,
                employment=self.employment,
                year=2026,
                starts_on=date(2026, 7, 7),
                ends_on=date(2026, 7, 7),
                portion=LeavePlanDay.Portion.AM,
                approve=True,
            )

    def test_continuous_working_days_skips_weekend(self):
        # Po 6.7.2026 – Pá 17.7.2026 = 10 pracovních dnů (bez So/Ne)
        n = continuous_working_days(
            date(2026, 7, 6), date(2026, 7, 17), count_holidays=True
        )
        self.assertEqual(n, 10)


class LeaveEntitlementDeadlineAdminTests(TestCase):
    """Ruční lhůty nároku smí měnit jen administrátor / superuser."""

    def setUp(self):
        from django.contrib.auth.models import Group, Permission

        from apps.accounts.roles import ROLE_ADMIN

        User = get_user_model()
        self.client = Client()
        self.employee = Employee.objects.create(
            first_name="Adam",
            last_name="AdminLhuta",
            internal_number="AL001",
        )
        self.employment = Employment.objects.create(
            employee=self.employee,
            started_on=date(2026, 1, 1),
            is_active=True,
            relation_type=Employment.RelationType.EMPLOYMENT,
            pay_regime=Employment.PayRegime.WAGE,
        )
        LeavePolicySettings.load()
        self.ent = LeaveEntitlement.objects.create(
            employment=self.employment,
            year=2026,
            entitled_minutes=9600,
            accrued_minutes=9600,
            preferred_use_by=date(2026, 12, 31),
            statutory_latest_use_by=date(2027, 12, 31),
            deadlines_manual=False,
        )
        self.admin_user = User.objects.create_user(
            username="real_admin",
            password="adminpass1",
            is_staff=True,
            is_superuser=False,
        )
        grp, _ = Group.objects.get_or_create(name=ROLE_ADMIN)
        self.admin_user.groups.add(grp)
        for codename in (
            "view_leaveentitlement",
            "change_leaveentitlement",
        ):
            perm = Permission.objects.get(
                content_type__app_label="leave",
                codename=codename,
            )
            self.admin_user.user_permissions.add(perm)

        self.staff_only = User.objects.create_user(
            username="staff_not_admin",
            password="adminpass1",
            is_staff=True,
            is_superuser=False,
        )
        for codename in (
            "view_leaveentitlement",
            "change_leaveentitlement",
        ):
            perm = Permission.objects.get(
                content_type__app_label="leave",
                codename=codename,
            )
            self.staff_only.user_permissions.add(perm)

    def _change_url(self):
        return reverse(
            "admin:leave_leaveentitlement_change",
            args=[self.ent.pk],
        )

    def _post_payload(self, *, statutory: date, include_deadlines: bool):
        payload = {
            "employment": self.employment.pk,
            "year": 2026,
            "accrued_minutes": 9600,
            "entitled_minutes": 9600,
            "carried_in_minutes": 0,
            "planned_minutes": 0,
            "taken_minutes": 0,
            "source_note": "",
        }
        if include_deadlines:
            payload["preferred_use_by"] = "2026-12-31"
            payload["statutory_latest_use_by"] = statutory.isoformat()
        return payload

    def test_admin_can_change_statutory_deadline(self):
        self.client.force_login(self.admin_user)
        resp = self.client.post(
            self._change_url(),
            self._post_payload(statutory=date(2028, 6, 30), include_deadlines=True),
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.ent.refresh_from_db()
        self.assertEqual(self.ent.statutory_latest_use_by, date(2028, 6, 30))
        self.assertTrue(self.ent.deadlines_manual)

    def test_staff_without_admin_role_cannot_change_deadline(self):
        original = self.ent.statutory_latest_use_by
        self.client.force_login(self.staff_only)
        # Readonly fields are omitted from POST by the browser; simulate
        # tampering by including them anyway — save_model must restore.
        resp = self.client.post(
            self._change_url(),
            self._post_payload(statutory=date(2029, 1, 1), include_deadlines=True),
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.ent.refresh_from_db()
        self.assertEqual(self.ent.statutory_latest_use_by, original)
        self.assertFalse(self.ent.deadlines_manual)

    def test_staff_sees_deadline_fields_readonly(self):
        from django.contrib import admin as dj_admin

        from apps.leave.admin import LeaveEntitlementAdmin

        ma = LeaveEntitlementAdmin(LeaveEntitlement, dj_admin.site)
        request = type("R", (), {"user": self.staff_only})()
        readonly = ma.get_readonly_fields(request, self.ent)
        for name in (
            "preferred_use_by",
            "statutory_latest_use_by",
            "deadlines_manual",
        ):
            self.assertIn(name, readonly)

        request_admin = type("R", (), {"user": self.admin_user})()
        readonly_admin = ma.get_readonly_fields(request_admin, self.ent)
        for name in (
            "preferred_use_by",
            "statutory_latest_use_by",
            "deadlines_manual",
        ):
            self.assertNotIn(name, readonly_admin)
