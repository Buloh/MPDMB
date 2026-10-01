from django.db import migrations, models


PALETTE = (
    "#166999",
    "#21759B",
    "#237A35",
    "#865600",
    "#B42318",
    "#6EC1E4",
    "#7B2D8E",
    "#C45C26",
    "#2F6F7E",
    "#5B6B2F",
)


def assign_colors(apps, schema_editor):
    ActivityLocation = apps.get_model("activities", "ActivityLocation")
    for index, loc in enumerate(
        ActivityLocation.objects.order_by("sort_order", "code", "id")
    ):
        loc.color = PALETTE[index % len(PALETTE)]
        loc.save(update_fields=["color"])


class Migration(migrations.Migration):

    dependencies = [
        ("activities", "0006_mapcity_mb_zoom_16"),
    ]

    operations = [
        migrations.AddField(
            model_name="activitylocation",
            name="color",
            field=models.CharField(
                default="#166999",
                help_text="Barva polygonu na mapě (#RRGGBB).",
                max_length=7,
                verbose_name="barva",
            ),
        ),
        migrations.RunPython(assign_colors, migrations.RunPython.noop),
    ]
