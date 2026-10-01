from datetime import time

from django.db import migrations


DEFAULT_TYPES = (
    {
        "code": "R",
        "name": "Ranní",
        "start_time": time(8, 0),
        "end_time": time(14, 0),
        "break_minutes": 0,
        "sort_order": 10,
        "applies_on_holiday": True,
    },
    {
        "code": "O",
        "name": "Odpolední",
        "start_time": time(14, 0),
        "end_time": time(22, 0),
        "break_minutes": 0,
        "sort_order": 20,
        "applies_on_holiday": True,
    },
    {
        "code": "N",
        "name": "Noční",
        "start_time": time(22, 0),
        "end_time": time(6, 0),
        "break_minutes": 0,
        "sort_order": 30,
        "applies_on_holiday": True,
    },
)


def seed_types(apps, schema_editor):
    ShiftType = apps.get_model("shifts", "ShiftType")
    for item in DEFAULT_TYPES:
        ShiftType.objects.update_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "start_time": item["start_time"],
                "end_time": item["end_time"],
                "break_minutes": item["break_minutes"],
                "sort_order": item["sort_order"],
                "applies_on_holiday": item["applies_on_holiday"],
                "counts_as_work": True,
                "is_active": True,
            },
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0002_shift_types_monthly"),
    ]

    operations = [
        migrations.RunPython(seed_types, noop),
    ]
