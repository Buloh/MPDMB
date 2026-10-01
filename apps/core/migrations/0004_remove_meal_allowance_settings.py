from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_meal_second_threshold"),
        ("attendance", "0003_meal_allowance_settings"),
    ]

    operations = [
        migrations.DeleteModel(
            name="MealAllowanceSettings",
        ),
    ]
