from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("activities", "0009_activityitem_location_optional"),
    ]

    operations = [
        migrations.AddField(
            model_name="activityitem",
            name="all_day",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Denní úkol mimo hodinovou mřížku (např. kontrola 4×).",
                verbose_name="celý den",
            ),
        ),
    ]
