from django.db import migrations


def bump_mb_zoom(apps, schema_editor):
    MapCity = apps.get_model("activities", "MapCity")
    MapCity.objects.filter(code="MB").update(default_zoom=16)


def revert_mb_zoom(apps, schema_editor):
    MapCity = apps.get_model("activities", "MapCity")
    MapCity.objects.filter(code="MB").update(default_zoom=14)


class Migration(migrations.Migration):

    dependencies = [
        ("activities", "0005_mapcity_help_and_mb_coords"),
    ]

    operations = [
        migrations.RunPython(bump_mb_zoom, revert_mb_zoom),
    ]
