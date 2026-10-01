# Plná práva administrátora, české názvy oprávnění, úklid osiřelých CT.

from django.db import migrations


def forwards(apps, schema_editor):
    from apps.accounts.permission_labels import (
        delete_orphaned_content_types,
        refresh_permission_names,
    )
    from apps.accounts.role_permissions import sync_role_group_permissions

    delete_orphaned_content_types()
    refresh_permission_names()
    sync_role_group_permissions()


def backwards(apps, schema_editor):
    # Částečný návrat: matice bez plných práv admina je v 0004 logice;
    # názvy oprávnění a smazané CT se neobnovují.
    from apps.accounts.role_permissions import sync_role_group_permissions

    sync_role_group_permissions()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_sync_role_permissions"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
