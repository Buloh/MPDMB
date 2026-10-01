from decimal import Decimal

from django.db import migrations, models


def seed_mb(apps, schema_editor):
    MapCity = apps.get_model("activities", "MapCity")
    MapCity.objects.update_or_create(
        code="MB",
        defaults={
            "name": "Mladá Boleslav",
            "center_lat": Decimal("50.411350"),
            "center_lon": Decimal("14.903180"),
            "default_zoom": 16,
            "is_active": True,
            "is_default": True,
            "sort_order": 10,
        },
    )


def unseed_mb(apps, schema_editor):
    MapCity = apps.get_model("activities", "MapCity")
    MapCity.objects.filter(code="MB").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("activities", "0003_activitylocation_parent"),
    ]

    operations = [
        migrations.CreateModel(
            name="MapCity",
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
                    "code",
                    models.CharField(max_length=32, unique=True, verbose_name="kód"),
                ),
                ("name", models.CharField(max_length=120, verbose_name="název")),
                (
                    "center_lat",
                    models.DecimalField(
                        decimal_places=6,
                        max_digits=9,
                        verbose_name="zeměpisná šířka",
                    ),
                ),
                (
                    "center_lon",
                    models.DecimalField(
                        decimal_places=6,
                        max_digits=9,
                        verbose_name="zeměpisná délka",
                    ),
                ),
                (
                    "default_zoom",
                    models.PositiveSmallIntegerField(
                        default=14,
                        help_text="Typicky 12–16.",
                        verbose_name="výchozí zoom",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True, default=True, verbose_name="aktivní"
                    ),
                ),
                (
                    "is_default",
                    models.BooleanField(
                        default=False,
                        help_text="Nejvýše jedno výchozí aktivní město.",
                        verbose_name="výchozí město",
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveSmallIntegerField(
                        default=100, verbose_name="pořadí"
                    ),
                ),
            ],
            options={
                "verbose_name": "mapové město",
                "verbose_name_plural": "mapová města",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.RunPython(seed_mb, unseed_mb),
    ]
