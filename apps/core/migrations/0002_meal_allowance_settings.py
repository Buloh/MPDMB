from django.db import migrations, models


def seed_meal_settings(apps, schema_editor):
    MealAllowanceSettings = apps.get_model("core", "MealAllowanceSettings")
    MealAllowanceSettings.objects.get_or_create(
        pk=1,
        defaults={"min_worked_minutes": 180, "is_active": True},
    )


def unseed_meal_settings(apps, schema_editor):
    MealAllowanceSettings = apps.get_model("core", "MealAllowanceSettings")
    MealAllowanceSettings.objects.filter(pk=1).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
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
                        help_text="Minimální čistá potvrzená práce v kalendářním dni.",
                        verbose_name="nárok od (minuty)",
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
        migrations.RunPython(seed_meal_settings, unseed_meal_settings),
    ]
