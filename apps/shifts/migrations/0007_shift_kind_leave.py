from datetime import time

from django.db import migrations, models


def seed_leave_type(apps, schema_editor):
    ShiftType = apps.get_model("shifts", "ShiftType")
    ShiftType.objects.update_or_create(
        code="D",
        defaults={
            "name": "Dovolená",
            "kind": "leave",
            "start_time": time(8, 0),
            "end_time": time(16, 0),
            "break_minutes": 0,
            "counts_as_work": False,
            "applies_on_holiday": False,
            "is_active": True,
            "sort_order": 90,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0006_shift_kind_and_qual_warn"),
    ]

    operations = [
        migrations.AlterField(
            model_name="shifttype",
            name="kind",
            field=models.CharField(
                choices=[
                    ("work", "Práce"),
                    ("standby", "Pohotovost"),
                    ("leave", "Dovolená"),
                ],
                db_index=True,
                default="work",
                help_text=(
                    "Pohotovost se nezapočítává do odpracovaných hodin (§ 140). "
                    "Dovolená patří do dlouhodobého plánu, ne do čisté práce."
                ),
                max_length=16,
                verbose_name="druh",
            ),
        ),
        migrations.RunPython(seed_leave_type, migrations.RunPython.noop),
    ]
