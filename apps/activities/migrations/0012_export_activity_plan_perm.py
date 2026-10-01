# Generated manually for export_activity_plan permission

from django.db import migrations


def grant_export_to_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    ActivityItem = apps.get_model("activities", "ActivityItem")
    ct = ContentType.objects.get_for_model(ActivityItem)
    perm, _ = Permission.objects.get_or_create(
        content_type=ct,
        codename="export_activity_plan",
        defaults={"name": "Může exportovat plán činností"},
    )
    if perm.name != "Může exportovat plán činností":
        perm.name = "Může exportovat plán činností"
        perm.save(update_fields=["name"])
    for role_name in ("administrátor", "vedoucí"):
        group = Group.objects.filter(name=role_name).first()
        if group is not None:
            group.permissions.add(perm)


def revoke_export_from_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    ActivityItem = apps.get_model("activities", "ActivityItem")
    ct = ContentType.objects.get_for_model(ActivityItem)
    perm = Permission.objects.filter(
        content_type=ct, codename="export_activity_plan"
    ).first()
    if perm is None:
        return
    for role_name in ("administrátor", "vedoucí"):
        group = Group.objects.filter(name=role_name).first()
        if group is not None:
            group.permissions.remove(perm)


class Migration(migrations.Migration):
    dependencies = [
        ("activities", "0011_activityitem_note_text"),
        ("accounts", "0002_create_roles"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="activityitem",
            options={
                "ordering": ["day", "sort_order", "starts_at", "id"],
                "permissions": [
                    (
                        "export_activity_plan",
                        "Může exportovat plán činností",
                    )
                ],
                "verbose_name": "činnost",
                "verbose_name_plural": "činnosti",
            },
        ),
        migrations.RunPython(grant_export_to_roles, revoke_export_from_roles),
    ]
