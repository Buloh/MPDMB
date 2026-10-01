from django.db import connection, migrations, models


def copy_or_seed_meal_settings(apps, schema_editor):
    MealAllowanceSettings = apps.get_model("attendance", "MealAllowanceSettings")
    table = "core_mealallowancesettings"
    existing = None
    with connection.cursor() as cursor:
        names = connection.introspection.table_names(cursor)
        if table in names:
            cursor.execute(
                f"SELECT min_worked_minutes, second_worked_minutes, is_active "
                f"FROM {table} WHERE id = 1"
            )
            existing = cursor.fetchone()

    if existing:
        min_m, second_m, active = existing
        MealAllowanceSettings.objects.update_or_create(
            pk=1,
            defaults={
                "min_worked_minutes": min_m,
                "second_worked_minutes": second_m,
                "is_active": bool(active),
            },
        )
    else:
        MealAllowanceSettings.objects.get_or_create(
            pk=1,
            defaults={
                "min_worked_minutes": 180,
                "second_worked_minutes": 720,
                "is_active": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("attendance", "0002_seed_absence_types"),
        ("core", "0003_meal_second_threshold"),
    ]

    operations = [
        migrations.CreateModel(
            name="MealAllowanceSettings",
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
                (
                    "min_worked_minutes",
                    models.PositiveIntegerField(
                        default=180,
                        help_text=(
                            "Minimální čistá potvrzená práce v kalendářním dni "
                            "pro 1. stravenku."
                        ),
                        verbose_name="1. stravenka od (minuty)",
                    ),
                ),
                (
                    "second_worked_minutes",
                    models.PositiveIntegerField(
                        blank=True,
                        default=720,
                        help_text=(
                            "Práh pro 2. stravenku ve stejném dni. "
                            "Prázdné = nejvýše 1 stravenka."
                        ),
                        null=True,
                        verbose_name="2. stravenka od (minuty)",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="aktivní"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="upraveno"),
                ),
            ],
            options={
                "verbose_name": "stravné",
                "verbose_name_plural": "stravné",
            },
        ),
        migrations.RunPython(copy_or_seed_meal_settings, migrations.RunPython.noop),
    ]
