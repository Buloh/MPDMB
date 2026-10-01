"""Automatické is_staff při roli administrátor."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import m2m_changed

from apps.accounts.roles import ROLE_ADMIN


def ensure_staff_for_admin_role(user) -> bool:
    """Pokud je ve skupině administrátor, zapne is_staff. Vrací True při změně."""
    if user is None or not getattr(user, "pk", None):
        return False
    if user.is_staff:
        return False
    if not user.groups.filter(name=ROLE_ADMIN).exists():
        return False
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return True


def user_groups_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    if action != "post_add":
        return

    User = get_user_model()
    if reverse:
        if getattr(instance, "name", None) != ROLE_ADMIN:
            return
        for user in User.objects.filter(pk__in=pk_set or []):
            ensure_staff_for_admin_role(user)
        return

    if not isinstance(instance, User):
        return
    if not pk_set:
        return
    if Group.objects.filter(pk__in=pk_set, name=ROLE_ADMIN).exists():
        ensure_staff_for_admin_role(instance)


def connect_staff_signals() -> None:
    User = get_user_model()
    m2m_changed.connect(
        user_groups_changed,
        sender=User.groups.through,
        dispatch_uid="accounts_admin_role_ensures_staff",
    )
