#!/usr/bin/env python
"""Kontrola limitu 1000 řádků u ručně spravovaných zdrojových souborů."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_LINES = 1000

SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".html",
    ".css",
    ".scss",
    ".sql",
    ".mdc",
}

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "staticfiles",
    "media",
    "dist",
    "build",
    ".tox",
}


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def count_lines(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def main() -> int:
    over_limit: list[tuple[Path, int]] = []
    checked = 0

    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if should_skip(path.relative_to(ROOT)):
            continue
        checked += 1
        lines = count_lines(path)
        if lines > MAX_LINES:
            over_limit.append((path.relative_to(ROOT), lines))

    if over_limit:
        print("Soubory nad limitem 1000 radku:")
        for rel, lines in over_limit:
            print(f"  {rel.as_posix()}: {lines}")
        print(f"Kontrola selhala ({len(over_limit)} / {checked}).")
        return 1

    print(f"OK: vsech {checked} zdrojovych souboru je do {MAX_LINES} radku.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
