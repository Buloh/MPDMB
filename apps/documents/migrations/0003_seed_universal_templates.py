# Založí záznamy univerzálních šablon (soubor .docx doplní ensure při prvním otevření).

from django.db import migrations


def seed_universal_rows(apps, schema_editor):
    DocumentTemplate = apps.get_model("documents", "DocumentTemplate")
    DocumentTemplate.objects.get_or_create(
        name="Univerzální – zaměstnanec",
        defaults={"scope": "zamestnanec", "is_active": True},
    )
    DocumentTemplate.objects.get_or_create(
        name="Univerzální – vozidlo",
        defaults={"scope": "vozidlo", "is_active": True},
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0002_sync_document_permissions"),
    ]

    operations = [
        migrations.RunPython(seed_universal_rows, noop),
    ]
