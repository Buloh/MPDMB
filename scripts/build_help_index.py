#!/usr/bin/env python
"""Sestavení fulltextového indexu HTML nápovědy SYNERA."""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELP_DIR = ROOT / "help"
PAGES_DIR = HELP_DIR / "pages"
INDEX_FILE = HELP_DIR / "search-index.json"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.headings: list[str] = []
        self.chunks: list[str] = []
        self._capture_title = False
        self._heading_level: int | None = None
        self._skip_depth = 0
        self._current: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "nav"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._capture_title = True
            self._current = []
        elif tag in {"h1", "h2", "h3"}:
            self._heading_level = int(tag[1])
            self._current = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        text = " ".join("".join(self._current).split())
        if tag == "title" and self._capture_title:
            self.title = text
            self._capture_title = False
            self._current = []
        elif tag in {"h1", "h2", "h3"} and self._heading_level is not None:
            if text:
                self.headings.append(text)
            self._heading_level = None
            self._current = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._capture_title or self._heading_level is not None:
            self._current.append(data)
        else:
            cleaned = " ".join(data.split())
            if cleaned:
                self.chunks.append(cleaned)


def extract_document(path: Path) -> dict:
    parser = _TextExtractor()
    parser.feed(path.read_text(encoding="utf-8"))
    rel = path.relative_to(HELP_DIR).as_posix()
    url = "/napoveda/" if rel == "index.html" else f"/napoveda/{rel}"
    title = parser.title or path.stem
    title = re.sub(r"\s*·\s*Nápověda SYNERA\s*$", "", title).strip() or path.stem
    text = " ".join(parser.chunks)
    return {
        "id": rel,
        "title": title,
        "url": url,
        "headings": parser.headings,
        "text": text,
    }


def main() -> int:
    if not HELP_DIR.is_dir():
        print(f"Chybí složka nápovědy: {HELP_DIR}", file=sys.stderr)
        return 1

    docs = [extract_document(HELP_DIR / "index.html")]
    for path in sorted(PAGES_DIR.glob("*.html")):
        docs.append(extract_document(path))

    INDEX_FILE.write_text(
        json.dumps(docs, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"OK: index {len(docs)} stran -> {INDEX_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
