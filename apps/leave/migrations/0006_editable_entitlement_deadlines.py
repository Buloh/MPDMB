"""Uložené editovatelné lhůty nároku roku (§ 218)."""

from datetime import date

from django.db import migrations, models


def fill_deadlines(apps, schema_editor):
    LeaveEntitlement = apps.get_model("leave", "LeaveEntitlement")
    for ent in LeaveEntitlement.objects.all().iterator():
        preferred = date(ent.year, 12, 31)
        if ent.entitled_minutes > 0 or ent.accrued_minutes > 0:
            statutory = date(ent.year + 1, 12, 31)
        else:
            statutory = None
        LeaveEntitlement.objects.filter(pk=ent.pk).update(
            preferred_use_by=preferred,
            statutory_latest_use_by=statutory,
            deadlines_manual=False,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("leave", "0005_entitlement_use_by_help"),
    ]

    operations = [
        migrations.AddField(
            model_name="leaveentitlement",
            name="preferred_use_by",
            field=models.DateField(
                blank=True,
                help_text="Výchozí 31.12. roku vzniku (§ 218 odst. 1). Lze upravit v adminu.",
                null=True,
                verbose_name="ideálně vyčerpat do",
            ),
        ),
        migrations.AddField(
            model_name="leaveentitlement",
            name="statutory_latest_use_by",
            field=models.DateField(
                blank=True,
                help_text=(
                    "Výchozí 31.12. následujícího roku (§ 218 odst. 3). "
                    "U výjimek (např. PN/MD/RD) upravte a zaškrtněte ruční lhůty."
                ),
                null=True,
                verbose_name="nejzazší vyčerpání nároku",
            ),
        ),
        migrations.AddField(
            model_name="leaveentitlement",
            name="deadlines_manual",
            field=models.BooleanField(
                default=False,
                help_text="Zapnuto = systém při obnově nároku lhůty nepřepisuje.",
                verbose_name="lhůty nastaveny ručně",
            ),
        ),
        migrations.AlterField(
            model_name="leaveentitlement",
            name="must_use_by",
            field=models.DateField(
                blank=True,
                help_text=(
                    "Jen při převodu z minulého roku (§ 218 odst. 3). "
                    "Lhůty vlastního nároku roku jsou výše (ideálně / nejzazší)."
                ),
                null=True,
                verbose_name="vyčerpat převod do",
            ),
        ),
        migrations.RunPython(fill_deadlines, noop_reverse),
    ]
