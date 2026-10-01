"""Přiřadí skupinu zaměstnanec uživatelům s kartou (nebo jednomu účtu)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.roles import ROLE_EMPLOYEE
from apps.employees.models import Employee


class Command(BaseCommand):
    help = (
        "Přiřadí roli „zaměstnanec“ uživatelům propojeným s kartou "
        "zaměstnance (jen pokud ještě nemají žádnou skupinu). "
        "S --replace přepíše stávající roli."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default="",
            help="Jen tento login (i bez karty zaměstnance).",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Vynutí groups.set([zaměstnanec]) i když už má jinou roli.",
        )

    def handle(self, *args, **options):
        group, _ = Group.objects.get_or_create(name=ROLE_EMPLOYEE)
        User = get_user_model()
        username = (options.get("username") or "").strip()
        replace = bool(options.get("replace"))

        if username:
            try:
                users = [User.objects.get(username=username)]
            except User.DoesNotExist as exc:
                raise CommandError(f"Uživatel „{username}“ neexistuje.") from exc
        else:
            user_ids = (
                Employee.objects.exclude(user_id=None)
                .values_list("user_id", flat=True)
                .distinct()
            )
            users = list(User.objects.filter(pk__in=user_ids).order_by("username"))

        added = 0
        already = 0
        skipped = 0
        for user in users:
            if user.groups.filter(pk=group.pk).exists() and user.groups.count() == 1:
                already += 1
                self.stdout.write(f"Již role zaměstnanec: {user.username}")
                continue
            if user.groups.exists() and not replace:
                skipped += 1
                self.stdout.write(
                    f"Přeskočen (má jinou roli): {user.username}"
                )
                continue
            user.groups.set([group])
            added += 1
            self.stdout.write(self.style.SUCCESS(f"Přiřazen: {user.username}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Hotovo. Nově přiřazeno: {added}, už OK: {already}, "
                f"přeskočeno: {skipped}, celkem: {added + already + skipped}."
            )
        )
