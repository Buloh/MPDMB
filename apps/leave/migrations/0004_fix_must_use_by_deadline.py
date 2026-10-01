"""Oprava lhůty vyčerpání převodu dovolené (§ 218 odst. 3 ZP)."""

from datetime import date

from django.db import migrations


def fix_must_use_by(apps, schema_editor):
    LeaveEntitlement = apps.get_model("leave", "LeaveEntitlement")
    for ent in LeaveEntitlement.objects.all().iterator():
        if ent.carried_in_minutes > 0:
            expected = date(ent.year, 12, 31)
        else:
            expected = None
        if ent.must_use_by != expected:
            LeaveEntitlement.objects.filter(pk=ent.pk).update(must_use_by=expected)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("leave", "0003_entitlement_accrued_continuous_holidays"),
    ]

    operations = [
        migrations.RunPython(fix_must_use_by, noop_reverse),
    ]
