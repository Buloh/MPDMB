from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Účty"

    def ready(self) -> None:
        from apps.accounts.staff_sync import connect_staff_signals

        connect_staff_signals()
