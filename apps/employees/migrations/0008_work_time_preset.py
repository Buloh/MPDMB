from django.db import migrations, models


def seed_presets(apps, schema_editor):
    WorkTimePreset = apps.get_model("employees", "WorkTimePreset")
    defaults = [
        ("40 hodin", 40 * 60, 10),
        ("38,75 hodin", 38 * 60 + 45, 20),
        ("37,5 hodin", 37 * 60 + 30, 30),
    ]
    for name, minutes, order in defaults:
        WorkTimePreset.objects.get_or_create(
            name=name,
            defaults={
                "weekly_minutes": minutes,
                "sort_order": order,
                "is_active": True,
            },
        )


def unseed_presets(apps, schema_editor):
    WorkTimePreset = apps.get_model("employees", "WorkTimePreset")
    WorkTimePreset.objects.filter(
        name__in=["40 hodin", "38,75 hodin", "37,5 hodin"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("employees", "0007_shift_kind_and_qual_warn"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkTimePreset",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=80, verbose_name="název")),
                (
                    "weekly_minutes",
                    models.PositiveIntegerField(
                        help_text="Např. 40 h = 2400, 38,75 h = 2325, 37,5 h = 2250.",
                        verbose_name="týdenní doba (min)",
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveSmallIntegerField(
                        default=100, verbose_name="pořadí"
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True, default=True, verbose_name="aktivní"
                    ),
                ),
            ],
            options={
                "verbose_name": "předvolba úvazku",
                "verbose_name_plural": "předvolby úvazku",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.RunPython(seed_presets, unseed_presets),
    ]
