# Doplní .docx do univerzálních šablon, pokud ještě nemají verzi.

from django.db import migrations


def fill_universal_files(apps, schema_editor):
    from apps.documents.services import ensure_universal_templates

    ensure_universal_templates(force_refresh=False)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0003_seed_universal_templates"),
        ("employees", "0004_seed_qualifications_migrate_licenses"),
        ("technika", "0002_seed_document_types"),
    ]

    operations = [
        migrations.RunPython(fill_universal_files, noop),
    ]
