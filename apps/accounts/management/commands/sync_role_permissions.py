"""Nastaví Django oprávnění skupin rolí podle názvu."""

from django.core.management.base import BaseCommand

from apps.accounts.permission_labels import (
    delete_orphaned_content_types,
    refresh_permission_names,
)
from apps.accounts.role_permissions import sync_role_group_permissions


class Command(BaseCommand):
    help = (
        "Přegeneruje české názvy oprávnění, odstraní osiřelé ContentType "
        "a přepíše oprávnění skupin administrátor / vedoucí / zaměstnanec / čtenář."
    )

    def handle(self, *args, **options):
        orphans = delete_orphaned_content_types()
        renamed = refresh_permission_names()
        self.stdout.write(
            self.style.SUCCESS(
                f"Osiřelé ContentType: smazáno {orphans}, přejmenováno práv: {renamed}"
            )
        )
        counts = sync_role_group_permissions()
        for role, n in counts.items():
            self.stdout.write(self.style.SUCCESS(f"{role}: {n} oprávnění"))
