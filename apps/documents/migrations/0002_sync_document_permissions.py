# Synchronizace práv skupin po přidání modelu dokumentů.

from django.db import migrations


def forwards(apps, schema_editor):
    from apps.accounts.permission_labels import refresh_permission_names
    from apps.accounts.role_permissions import sync_role_group_permissions

    refresh_permission_names()
    sync_role_group_permissions()


def backwards(apps, schema_editor):
    from apps.accounts.role_permissions import sync_role_group_permissions

    sync_role_group_permissions()


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0001_initial_documents"),
        ("accounts", "0005_admin_all_perms_czech_names"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
