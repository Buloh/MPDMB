from django.db import migrations


def seed_document_types(apps, schema_editor):
    VehicleDocumentType = apps.get_model("technika", "VehicleDocumentType")
    defaults = (
        {
            "code": "stk",
            "name": "Technická kontrola (STK)",
            "requires_number": True,
            "warn_days_before": 30,
            "sort_order": 10,
        },
        {
            "code": "pojistka",
            "name": "Povinné ručení / pojistka",
            "requires_number": True,
            "warn_days_before": 30,
            "sort_order": 20,
        },
    )
    for item in defaults:
        VehicleDocumentType.objects.update_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "requires_number": item["requires_number"],
                "warn_days_before": item["warn_days_before"],
                "sort_order": item["sort_order"],
                "is_active": True,
            },
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("technika", "0001_initial_vehicle"),
    ]

    operations = [
        migrations.RunPython(seed_document_types, noop),
    ]
