from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import AuditEvent
from apps.employees.models import (
    Employee,
    Employment,
    QualificationType,
    WorkTimePreset,
    WorkTimeProfile,
)
from apps.workplaces.models import EmployeeWorkplace, Workplace


class EmployeesWorkplacesTests(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="Holub",
            password="22552255",
            is_staff=True,
            is_superuser=True,
        )
        self.plain = User.objects.create_user(
            username="ctenar",
            password="ctenar123",
            is_staff=False,
        )
        self.license_type = QualificationType.objects.get(code="ridicsky_prukaz")
        self.elektro_type = QualificationType.objects.get(code="elektro")
        self.employee = Employee.objects.create(
            first_name="Jana",
            last_name="Novakova",
            internal_number="E001",
            job_title="Obsluha",
        )
        Employment.objects.create(
            employee=self.employee,
            started_on=date(2026, 1, 1),
            relation_type=Employment.RelationType.EMPLOYMENT,
        )
        self.workplace = Workplace.objects.create(
            name="Parkovaci dum Centrum",
            address="Hlavni 1",
        )

    def _empty_qual_formset(self, total=1):
        data = {
            "qual-TOTAL_FORMS": str(total),
            "qual-INITIAL_FORMS": "0",
            "qual-MIN_NUM_FORMS": "0",
            "qual-MAX_NUM_FORMS": "1000",
        }
        for index in range(total):
            data.update(
                {
                    f"qual-{index}-qualification_type": "",
                    f"qual-{index}-number": "",
                    f"qual-{index}-categories": "",
                    f"qual-{index}-valid_from": "",
                    f"qual-{index}-valid_until": "",
                    f"qual-{index}-issued_by": "",
                    f"qual-{index}-notes": "",
                    f"qual-{index}-is_active": "on",
                }
            )
        return data

    def _empty_wp_formset(self, total=1, initial=0):
        data = {
            "wp-TOTAL_FORMS": str(total),
            "wp-INITIAL_FORMS": str(initial),
            "wp-MIN_NUM_FORMS": "0",
            "wp-MAX_NUM_FORMS": "1000",
        }
        for index in range(total):
            data.update(
                {
                    f"wp-{index}-workplace": "",
                    f"wp-{index}-valid_from": "",
                    f"wp-{index}-valid_to": "",
                    f"wp-{index}-id": "",
                }
            )
        return data

    def _default_work_time(self, valid_from="2026-03-01", agreed=2400):
        return {
            "wt-preset": "",
            "wt-valid_from": valid_from,
            "wt-statutory_weekly_minutes": str(agreed),
            "wt-agreed_weekly_minutes": str(agreed),
            "wt-regime": "single",
            "wt-distribution": "even",
        }

    def _leave_settings(self, extra_weeks=0, half_day=""):
        return {
            "leave-extra_weeks": str(extra_weeks),
            "leave-allow_half_day_choice": half_day,
        }

    def test_employee_list_requires_login(self):
        response = self.client.get(reverse("employee_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_employee_list_forbidden_for_non_staff(self):
        self.client.login(username="ctenar", password="ctenar123")
        response = self.client.get(reverse("employee_list"))
        self.assertEqual(response.status_code, 403)

    def test_employee_list_ok_for_staff(self):
        self.client.login(username="Holub", password="22552255")
        response = self.client.get(reverse("employee_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Novakova")
        self.assertContains(response, "01.01.2026")

    def test_employee_create_with_qualifications(self):
        self.client.login(username="Holub", password="22552255")
        payload = {
            "first_name": "Petr",
            "last_name": "Svoboda",
            "internal_number": "E002",
            "job_title": "Technik",
            "phone": "777111222",
            "email": "petr@example.com",
            "work_contact": "",
            "notes": "",
            "user": "",
            "is_active": "on",
            "emp-relation_type": "PP",
            "emp-started_on": "2026-03-01",
            "emp-ended_on": "",
            "emp-payroll_number": "00042",
            "emp-pay_regime": "mzda",
            "emp-job_title": "Technik",
            "emp-is_active": "on",
            "qual-TOTAL_FORMS": "2",
            "qual-INITIAL_FORMS": "0",
            "qual-MIN_NUM_FORMS": "0",
            "qual-MAX_NUM_FORMS": "1000",
            "qual-0-qualification_type": str(self.license_type.pk),
            "qual-0-number": "AB123456",
            "qual-0-categories": "B",
            "qual-0-valid_from": "",
            "qual-0-valid_until": "2028-06-15",
            "qual-0-issued_by": "",
            "qual-0-notes": "",
            "qual-0-is_active": "on",
            "qual-1-qualification_type": str(self.elektro_type.pk),
            "qual-1-number": "EL-99",
            "qual-1-categories": "",
            "qual-1-valid_from": "2024-01-01",
            "qual-1-valid_until": "2020-01-01",
            "qual-1-issued_by": "TIČR",
            "qual-1-notes": "",
            "qual-1-is_active": "on",
        }
        payload.update(self._default_work_time("2026-03-01", 2400))
        payload.update(self._empty_wp_formset())
        payload.update(self._leave_settings())
        response = self.client.post(reverse("employee_create"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Platnost do nesmí být dříve než platnost od")

        payload["qual-1-valid_until"] = "2025-01-01"
        response = self.client.post(reverse("employee_create"), payload)
        self.assertEqual(response.status_code, 302)
        emp = Employee.objects.get(internal_number="E002")
        self.assertEqual(emp.qualifications.count(), 2)
        license_q = emp.qualifications.get(qualification_type=self.license_type)
        self.assertEqual(license_q.number, "AB123456")
        self.assertEqual(license_q.valid_until, date(2028, 6, 15))
        elektro_q = emp.qualifications.get(qualification_type=self.elektro_type)
        self.assertTrue(elektro_q.is_expired)
        self.assertTrue(
            AuditEvent.objects.filter(
                object_type="Employee",
                object_id=str(emp.pk),
                operation="employee_create",
            ).exists()
        )

        detail = self.client.get(reverse("employee_detail", args=[emp.pk]))
        self.assertContains(detail, "15.06.2028")
        self.assertContains(detail, "01.01.2025")
        self.assertContains(detail, "prošlá")
        self.assertContains(detail, "Řidičský průkaz")
        self.assertContains(detail, "Odborná způsobilost elektro")

        listing = self.client.get(reverse("employee_list"))
        self.assertContains(listing, "prošlé")

        response = self.client.post(reverse("employee_archive", args=[emp.pk]))
        self.assertEqual(response.status_code, 302)
        emp.refresh_from_db()
        self.assertFalse(emp.is_active)

    def test_employment_end_before_start_rejected(self):
        self.client.login(username="Holub", password="22552255")
        payload = {
            "first_name": "Eva",
            "last_name": "Dvorakova",
            "internal_number": "E003",
            "job_title": "",
            "phone": "",
            "email": "",
            "work_contact": "",
            "notes": "",
            "user": "",
            "is_active": "on",
            "emp-relation_type": "PP",
            "emp-started_on": "2026-05-01",
            "emp-ended_on": "2026-04-01",
            "emp-payroll_number": "",
            "emp-pay_regime": "mzda",
            "emp-job_title": "",
            "emp-is_active": "on",
        }
        payload.update(self._empty_qual_formset())
        payload.update(self._default_work_time("2026-05-01"))
        payload.update(self._empty_wp_formset())
        payload.update(self._leave_settings())
        response = self.client.post(reverse("employee_create"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Den ukončení nesmí být dříve než den nástupu")
        self.assertFalse(Employee.objects.filter(internal_number="E003").exists())

    def test_default_qualification_types_seeded(self):
        self.assertTrue(
            QualificationType.objects.filter(code="ridicsky_prukaz").exists()
        )
        self.assertTrue(QualificationType.objects.filter(code="elektro").exists())
        self.assertEqual(
            QualificationType.objects.get(code="ridicsky_prukaz").warn_days_before, 30
        )
        self.assertEqual(
            QualificationType.objects.get(code="elektro").warn_days_before, 60
        )

    def test_qualification_alerts_on_home(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.employees.models import EmployeeQualification
        from apps.employees.services import qualification_alerts_for_user

        today = timezone.localdate()
        EmployeeQualification.objects.create(
            employee=self.employee,
            qualification_type=self.license_type,
            number="AB123",
            categories="B",
            valid_until=today + timedelta(days=10),
        )
        EmployeeQualification.objects.create(
            employee=self.employee,
            qualification_type=self.elektro_type,
            number="E-1",
            valid_until=today - timedelta(days=2),
        )
        alerts = qualification_alerts_for_user(self.staff)
        self.assertEqual(len(alerts), 2)
        severities = {a["severity"] for a in alerts}
        self.assertEqual(severities, {"soon", "expired"})

        self.client.login(username="Holub", password="22552255")
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kvalifikace k řešení")
        self.assertContains(response, "Řidičský průkaz")

    def test_workplace_list_and_assign(self):
        self.client.login(username="Holub", password="22552255")
        response = self.client.get(reverse("workplace_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Parkovaci dum Centrum")

        response = self.client.post(
            reverse("workplace_assign", args=[self.workplace.pk]),
            {
                "employee": self.employee.pk,
                "workplace": self.workplace.pk,
                "valid_from": "2026-09-01",
                "valid_to": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            EmployeeWorkplace.objects.filter(
                employee=self.employee,
                workplace=self.workplace,
                valid_from=date(2026, 9, 1),
            ).exists()
        )

    def test_workplace_assign_before_employment_rejected(self):
        self.client.login(username="Holub", password="22552255")
        Employment.objects.filter(employee=self.employee).update(
            started_on=date(2026, 11, 1)
        )
        response = self.client.post(
            reverse("workplace_assign", args=[self.workplace.pk]),
            {
                "employee": self.employee.pk,
                "workplace": self.workplace.pk,
                "valid_from": "2026-10-01",
                "valid_to": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "nesmí začínat dříve než den nástupu")
        self.assertFalse(
            EmployeeWorkplace.objects.filter(employee=self.employee).exists()
        )

    def test_employee_workplace_model_clean_before_start(self):
        from django.core.exceptions import ValidationError

        Employment.objects.filter(employee=self.employee).update(
            started_on=date(2026, 11, 1)
        )
        assignment = EmployeeWorkplace(
            employee=self.employee,
            workplace=self.workplace,
            valid_from=date(2026, 10, 1),
        )
        with self.assertRaises(ValidationError) as ctx:
            assignment.full_clean()
        self.assertIn("valid_from", ctx.exception.message_dict)
        self.assertIn(
            "nástupu",
            str(ctx.exception.message_dict["valid_from"]),
        )

    def test_admin_branding(self):
        self.client.login(username="Holub", password="22552255")
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SYNERA")
        self.assertNotContains(response, "Správa systému Django")
        self.assertNotContains(response, "MPDMB – Provoz parkovacích domů")

    def test_employee_edit_sets_uvazek_and_workplace(self):
        self.client.login(username="Holub", password="22552255")
        employment = self.employee.employments.get()
        preset = WorkTimePreset.objects.get(name="37,5 hodin")
        payload = {
            "first_name": self.employee.first_name,
            "last_name": self.employee.last_name,
            "internal_number": self.employee.internal_number,
            "job_title": self.employee.job_title,
            "phone": "",
            "email": "",
            "work_contact": "",
            "notes": "",
            "user": "",
            "is_active": "on",
            "emp-relation_type": employment.relation_type,
            "emp-started_on": "2026-01-01",
            "emp-ended_on": "",
            "emp-payroll_number": "",
            "emp-pay_regime": employment.pay_regime,
            "emp-job_title": "",
            "emp-is_active": "on",
            "wt-preset": str(preset.pk),
            "wt-valid_from": "2026-01-01",
            "wt-statutory_weekly_minutes": "2400",
            "wt-agreed_weekly_minutes": "2400",
            "wt-regime": "single",
            "wt-distribution": "even",
            "wp-TOTAL_FORMS": "1",
            "wp-INITIAL_FORMS": "0",
            "wp-MIN_NUM_FORMS": "0",
            "wp-MAX_NUM_FORMS": "1000",
            "wp-0-workplace": str(self.workplace.pk),
            "wp-0-valid_from": "2026-01-01",
            "wp-0-valid_to": "",
            "wp-0-id": "",
        }
        payload.update(self._empty_qual_formset())
        payload.update(self._leave_settings())
        response = self.client.post(
            reverse("employee_edit", args=[self.employee.pk]), payload
        )
        self.assertEqual(response.status_code, 302)
        profile = WorkTimeProfile.objects.get(employment=employment)
        self.assertEqual(profile.agreed_weekly_minutes, 2250)
        self.assertEqual(profile.statutory_weekly_minutes, 2250)
        self.assertTrue(
            EmployeeWorkplace.objects.filter(
                employee=self.employee,
                workplace=self.workplace,
            ).exists()
        )
        detail = self.client.get(reverse("employee_detail", args=[self.employee.pk]))
        self.assertContains(detail, "7:30 h/týden")

        edit_get = self.client.get(reverse("employee_edit", args=[self.employee.pk]))
        self.assertEqual(edit_get.status_code, 200)
        self.assertContains(edit_get, "form-compact")
        self.assertContains(
            edit_get,
            f'value="{preset.pk}" selected',
        )
        self.assertContains(edit_get, 'data-minutes="2250"')
        self.assertContains(edit_get, "work-time-preset.js")
        self.assertContains(edit_get, "Povolit půldenní dovolenou")

    def test_workplace_overlap_rejected_on_employee_edit(self):
        self.client.login(username="Holub", password="22552255")
        other = Workplace.objects.create(name="Druhe WP")
        employment = self.employee.employments.get()
        payload = {
            "first_name": self.employee.first_name,
            "last_name": self.employee.last_name,
            "internal_number": self.employee.internal_number,
            "job_title": "",
            "phone": "",
            "email": "",
            "work_contact": "",
            "notes": "",
            "user": "",
            "is_active": "on",
            "emp-relation_type": employment.relation_type,
            "emp-started_on": "2026-01-01",
            "emp-ended_on": "",
            "emp-payroll_number": "",
            "emp-pay_regime": employment.pay_regime,
            "emp-job_title": "",
            "emp-is_active": "on",
            "wt-preset": "",
            "wt-valid_from": "2026-01-01",
            "wt-statutory_weekly_minutes": "2400",
            "wt-agreed_weekly_minutes": "2400",
            "wt-regime": "single",
            "wt-distribution": "even",
            "wp-TOTAL_FORMS": "2",
            "wp-INITIAL_FORMS": "0",
            "wp-MIN_NUM_FORMS": "0",
            "wp-MAX_NUM_FORMS": "1000",
            "wp-0-workplace": str(self.workplace.pk),
            "wp-0-valid_from": "2026-01-01",
            "wp-0-valid_to": "",
            "wp-0-id": "",
            "wp-1-workplace": str(other.pk),
            "wp-1-valid_from": "2026-06-01",
            "wp-1-valid_to": "",
            "wp-1-id": "",
        }
        payload.update(self._empty_qual_formset())
        payload.update(self._leave_settings())
        response = self.client.post(
            reverse("employee_edit", args=[self.employee.pk]), payload
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "nesmí překrývat")
        self.assertEqual(
            EmployeeWorkplace.objects.filter(employee=self.employee).count(), 0
        )

    def test_workplace_before_employment_start_rejected(self):
        self.client.login(username="Holub", password="22552255")
        employment = self.employee.employments.get()
        payload = {
            "first_name": self.employee.first_name,
            "last_name": self.employee.last_name,
            "internal_number": self.employee.internal_number,
            "job_title": "",
            "phone": "",
            "email": "",
            "work_contact": "",
            "notes": "",
            "user": "",
            "is_active": "on",
            "emp-relation_type": employment.relation_type,
            "emp-started_on": "2026-11-01",
            "emp-ended_on": "",
            "emp-payroll_number": "",
            "emp-pay_regime": employment.pay_regime,
            "emp-job_title": "",
            "emp-is_active": "on",
            "wt-preset": "",
            "wt-valid_from": "2026-11-01",
            "wt-statutory_weekly_minutes": "2400",
            "wt-agreed_weekly_minutes": "2400",
            "wt-regime": "single",
            "wt-distribution": "even",
            "wp-TOTAL_FORMS": "1",
            "wp-INITIAL_FORMS": "0",
            "wp-MIN_NUM_FORMS": "0",
            "wp-MAX_NUM_FORMS": "1000",
            "wp-0-workplace": str(self.workplace.pk),
            "wp-0-valid_from": "2026-10-01",
            "wp-0-valid_to": "",
            "wp-0-id": "",
        }
        payload.update(self._empty_qual_formset())
        payload.update(self._leave_settings())
        response = self.client.post(
            reverse("employee_edit", args=[self.employee.pk]), payload
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "nesmí začínat dříve než den nástupu")
        self.assertEqual(
            EmployeeWorkplace.objects.filter(employee=self.employee).count(), 0
        )

    def test_mid_month_uvazek_change_closes_old_profile(self):
        self.client.login(username="Holub", password="22552255")
        employment = self.employee.employments.get()
        WorkTimeProfile.objects.create(
            employment=employment,
            valid_from=date(2026, 1, 1),
            statutory_weekly_minutes=2250,
            agreed_weekly_minutes=2250,
        )
        payload = {
            "first_name": self.employee.first_name,
            "last_name": self.employee.last_name,
            "internal_number": self.employee.internal_number,
            "job_title": "",
            "phone": "",
            "email": "",
            "work_contact": "",
            "notes": "",
            "user": "",
            "is_active": "on",
            "emp-relation_type": employment.relation_type,
            "emp-started_on": "2026-01-01",
            "emp-ended_on": "",
            "emp-payroll_number": "",
            "emp-pay_regime": employment.pay_regime,
            "emp-job_title": "",
            "emp-is_active": "on",
            "wt-preset": "",
            "wt-valid_from": "2026-09-16",
            "wt-statutory_weekly_minutes": "2400",
            "wt-agreed_weekly_minutes": "2400",
            "wt-regime": "single",
            "wt-distribution": "even",
        }
        payload.update(self._empty_qual_formset())
        payload.update(self._empty_wp_formset())
        payload.update(self._leave_settings())
        response = self.client.post(
            reverse("employee_edit", args=[self.employee.pk]), payload
        )
        self.assertEqual(response.status_code, 302)
        profiles = list(
            WorkTimeProfile.objects.filter(employment=employment).order_by(
                "valid_from"
            )
        )
        self.assertEqual(len(profiles), 2)
        self.assertEqual(profiles[0].valid_to, date(2026, 9, 15))
        self.assertEqual(profiles[0].agreed_weekly_minutes, 2250)
        self.assertEqual(profiles[1].valid_from, date(2026, 9, 16))
        self.assertEqual(profiles[1].agreed_weekly_minutes, 2400)


class EmployeeUserSyncTests(TestCase):
    def test_sync_copies_name_and_email_to_user(self):
        from apps.employees.user_sync import sync_user_from_employee

        User = get_user_model()
        account = User.objects.create_user(
            username="link_me",
            password="x",
            first_name="",
            last_name="",
            email="",
        )
        employee = Employee.objects.create(
            first_name="Jana",
            last_name="Novakova",
            internal_number="SYNC01",
            email="jana@example.com",
            user=account,
        )
        self.assertTrue(sync_user_from_employee(employee))
        account.refresh_from_db()
        self.assertEqual(account.first_name, "Jana")
        self.assertEqual(account.last_name, "Novakova")
        self.assertEqual(account.email, "jana@example.com")
        self.assertFalse(sync_user_from_employee(employee))
