# Přejmenování uložených názvů oprávnění Can add/… na češtinu.

from django.db import migrations

_PREFIXES = (
    ("Can add ", "Přidat: "),
    ("Can change ", "Změnit: "),
    ("Can delete ", "Smazat: "),
    ("Can view ", "Zobrazit: "),
)


def rename_permission_names(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    for perm in Permission.objects.all().iterator():
        name = perm.name
        new_name = name
        for en, cs in _PREFIXES:
            if name.startswith(en):
                new_name = cs + name[len(en) :]
                break
        if new_name != name:
            perm.name = new_name
            perm.save(update_fields=["name"])


def revert_permission_names(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    reverse = (
        ("Přidat: ", "Can add "),
        ("Změnit: ", "Can change "),
        ("Smazat: ", "Can delete "),
        ("Zobrazit: ", "Can view "),
    )
    for perm in Permission.objects.all().iterator():
        name = perm.name
        new_name = name
        for cs, en in reverse:
            if name.startswith(cs):
                new_name = en + name[len(cs) :]
                break
        if new_name != name:
            perm.name = new_name
            perm.save(update_fields=["name"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_create_roles"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("activities", "0012_export_activity_plan_perm"),
    ]

    operations = [
        migrations.RunPython(rename_permission_names, revert_permission_names),
    ]
