"""Zajisti lokálního vývojového administrátora Holub."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.accounts.roles import ROLE_ADMIN

DEV_USERNAME = "Holub"
DEV_PASSWORD = "22552255"


class Command(BaseCommand):
    help = "Vytvoří nebo aktualizuje vývojového administrátora Holub."

    def handle(self, *args, **options):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=DEV_USERNAME,
            defaults={
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(DEV_PASSWORD)
        user.save()

        admin_group, _ = Group.objects.get_or_create(name=ROLE_ADMIN)
        user.groups.add(admin_group)

        if created:
            self.stdout.write(self.style.SUCCESS(f"Vytvořen účet {DEV_USERNAME}."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Aktualizován účet {DEV_USERNAME}.")
            )
        self.stdout.write(
            self.style.SUCCESS(f"Zařazen do skupiny {ROLE_ADMIN}.")
        )
