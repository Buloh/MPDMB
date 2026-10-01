from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("activities", "0010_activityitem_all_day"),
    ]

    operations = [
        migrations.AlterField(
            model_name="activityitem",
            name="note",
            field=models.TextField(blank=True, verbose_name="poznámka"),
        ),
    ]
