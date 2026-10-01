#!/usr/bin/env python
"""Vstupní bod správy projektu MPDMB."""

import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Nepodařilo se importovat Django. Ověřte aktivaci .venv "
            "a instalaci závislostí z requirements.txt."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
