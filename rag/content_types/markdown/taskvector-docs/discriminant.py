from __future__ import annotations

from pathlib import Path

CONTENT_KIND = "taskvector-docs"
PRIORITY = 1


def matches(path: Path, data: object = None) -> bool:
    p = path.as_posix().lower()
    return ("docs/" in p) and path.suffix.lower() == ".md"
