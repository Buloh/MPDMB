from django.db import migrations


TYPES = (
    ("kontrola", "Kontrola", "none", 10),
    ("obsluha", "Obsluha", "car", 20),
    ("pochuzka", "Pochůzka", "walk", 30),
)


def seed(apps, schema_editor):
    ActivityType = apps.get_model("activities", "ActivityType")
    for code, name, mode, order in TYPES:
        ActivityType.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "travel_mode": mode,
                "is_active": True,
                "sort_order": order,
            },
        )


def unseed(apps, schema_editor):
    ActivityType = apps.get_model("activities", "ActivityType")
    ActivityType.objects.filter(code__in=[t[0] for t in TYPES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("activities", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
