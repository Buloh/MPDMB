from django.db import migrations, models


def seed_second_threshold(apps, schema_editor):
    MealAllowanceSettings = apps.get_model("core", "MealAllowanceSettings")
    MealAllowanceSettings.objects.filter(pk=1, second_worked_minutes__isnull=True).update(
        second_worked_minutes=720
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_meal_allowance_settings"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mealallowancesettings",
            name="min_worked_minutes",
            field=models.PositiveIntegerField(
                default=180,
                help_text=(
                    "Minimální čistá potvrzená práce v kalendářním dni pro 1. stravenku."
                ),
                verbose_name="1. stravenka od (minuty)",
            ),
        ),
        migrations.AddField(
            model_name="mealallowancesettings",
            name="second_worked_minutes",
            field=models.PositiveIntegerField(
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
        migrations.RunPython(seed_second_threshold, migrations.RunPython.noop),
    ]
