"""Uživatelský účet oddělený od evidence zaměstnance."""

from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Přihlašovací účet MPDMB.

    Zaměstnanec nemusí mít účet; vazba na zaměstnance vznikne
    v aplikaci employees v pozdější etapě.
    """

    class Meta:
        verbose_name = "uživatel"
        verbose_name_plural = "uživatelé"
        ordering = ["username"]

    def __str__(self) -> str:
        full_name = self.get_full_name().strip()
        return full_name or self.username
