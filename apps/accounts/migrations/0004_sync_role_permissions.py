# Synchronizace oprávnění skupin rolí podle názvu.

from django.db import migrations


def forwards(apps, schema_editor):
    # Importovat až po migracích modelů — funkce používá živé Permission/Group.
    from apps.accounts.role_permissions import sync_role_group_permissions

    sync_role_group_permissions()


def backwards(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in ("administrátor", "vedoucí", "zaměstnanec", "čtenář"):
        group = Group.objects.filter(name=name).first()
        if group is not None:
            group.permissions.clear()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_czech_permission_names"),
        ("activities", "0012_export_activity_plan_perm"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
