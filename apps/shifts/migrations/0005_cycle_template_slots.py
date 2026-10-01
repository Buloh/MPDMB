"""Migrace šablon na cyklus + sloty a kotvu přiřazení."""

from django.db import migrations, models
import django.db.models.deletion


WEEKDAY_FIELDS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def forwards_slots(apps, schema_editor):
    ScheduleTemplate = apps.get_model("shifts", "ScheduleTemplate")
    ScheduleTemplateSlot = apps.get_model("shifts", "ScheduleTemplateSlot")
    EmployeeScheduleAssignment = apps.get_model(
        "shifts", "EmployeeScheduleAssignment"
    )
    for tmpl in ScheduleTemplate.objects.all():
        tmpl.cycle_length = 7
        tmpl.save(update_fields=["cycle_length"])
        for i, field in enumerate(WEEKDAY_FIELDS):
            st_id = getattr(tmpl, f"{field}_id", None)
            ScheduleTemplateSlot.objects.update_or_create(
                template=tmpl,
                day_index=i,
                defaults={"shift_type_id": st_id},
            )
    for asg in EmployeeScheduleAssignment.objects.all():
        if not asg.cycle_anchor_date:
            asg.cycle_anchor_date = asg.valid_from
            asg.save(update_fields=["cycle_anchor_date"])


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("shifts", "0004_schedule_templates"),
        ("employees", "0005_remove_drivers_license_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduletemplate",
            name="cycle_length",
            field=models.PositiveSmallIntegerField(
                choices=[(7, "7 dní (týden)"), (14, "14 dní (krátký/dlouhý)")],
                default=7,
                verbose_name="délka cyklu (dny)",
            ),
        ),
        migrations.CreateModel(
            name="ScheduleTemplateSlot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("day_index", models.PositiveSmallIntegerField(verbose_name="den v cyklu")),
                (
                    "shift_type",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="shifts.shifttype",
                        verbose_name="typ směny",
                    ),
                ),
                (
                    "template",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="slots",
                        to="shifts.scheduletemplate",
                        verbose_name="šablona",
                    ),
                ),
            ],
            options={
                "verbose_name": "den šablony",
                "verbose_name_plural": "dny šablony",
                "ordering": ["day_index"],
            },
        ),
        migrations.AddConstraint(
            model_name="scheduletemplateslot",
            constraint=models.UniqueConstraint(
                fields=("template", "day_index"),
                name="uniq_schedule_template_day_index",
            ),
        ),
        migrations.AddField(
            model_name="employeescheduleassignment",
            name="cycle_anchor_date",
            field=models.DateField(
                blank=True,
                help_text="Datum, které odpovídá 1. dni šablony (index 0). Pro fázový posun u nepřetržitého provozu.",
                null=True,
                verbose_name="kotva cyklu",
            ),
        ),
        migrations.RunPython(forwards_slots, backwards_noop),
        migrations.AlterField(
            model_name="employeescheduleassignment",
            name="cycle_anchor_date",
            field=models.DateField(
                help_text="Datum, které odpovídá 1. dni šablony (index 0). Pro fázový posun u nepřetržitého provozu.",
                verbose_name="kotva cyklu",
            ),
        ),
        migrations.RemoveField(model_name="scheduletemplate", name="monday"),
        migrations.RemoveField(model_name="scheduletemplate", name="tuesday"),
        migrations.RemoveField(model_name="scheduletemplate", name="wednesday"),
        migrations.RemoveField(model_name="scheduletemplate", name="thursday"),
        migrations.RemoveField(model_name="scheduletemplate", name="friday"),
        migrations.RemoveField(model_name="scheduletemplate", name="saturday"),
        migrations.RemoveField(model_name="scheduletemplate", name="sunday"),
    ]
