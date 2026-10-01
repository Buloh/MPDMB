from django.db import migrations


DEFAULT_TYPES = (
    {
        "code": "ridicsky_prukaz",
        "name": "Řidičský průkaz",
        "description": "Řidičské oprávnění.",
        "requires_number": True,
        "requires_categories": True,
        "sort_order": 10,
    },
    {
        "code": "elektro",
        "name": "Odborná způsobilost elektro",
        "description": "Zkoušky a osvědčení pro práci na elektrických zařízeních.",
        "requires_number": True,
        "requires_categories": False,
        "sort_order": 20,
    },
)


def seed_and_migrate_licenses(apps, schema_editor):
    QualificationType = apps.get_model("employees", "QualificationType")
    Employee = apps.get_model("employees", "Employee")
    EmployeeQualification = apps.get_model("employees", "EmployeeQualification")

    for item in DEFAULT_TYPES:
        QualificationType.objects.update_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "description": item["description"],
                "requires_number": item["requires_number"],
                "requires_categories": item["requires_categories"],
                "sort_order": item["sort_order"],
                "is_active": True,
            },
        )

    license_type = QualificationType.objects.get(code="ridicsky_prukaz")
    for employee in Employee.objects.all():
        has_data = (
            (employee.drivers_license_number or "").strip()
            or (employee.drivers_license_categories or "").strip()
            or employee.drivers_license_valid_until is not None
        )
        if not has_data:
            continue
        EmployeeQualification.objects.create(
            employee=employee,
            qualification_type=license_type,
            number=(employee.drivers_license_number or "").strip(),
            categories=(employee.drivers_license_categories or "").strip(),
            valid_until=employee.drivers_license_valid_until,
            is_active=True,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("employees", "0003_qualification_types"),
    ]

    operations = [
        migrations.RunPython(seed_and_migrate_licenses, noop_reverse),
    ]
