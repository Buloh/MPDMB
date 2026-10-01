"""Vývojové nastavení MPDMB (HTTP, síťový přístup v rámci firmy/VPN)."""

from .base import *  # noqa: F403

DEBUG = True

if not ALLOWED_HOSTS:  # noqa: F405
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]  # noqa: F405

# Vývoj běží přes HTTP; Secure cookies zapíná production.py.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
