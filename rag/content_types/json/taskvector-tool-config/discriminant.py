from __future__ import annotations

from pathlib import Path

CONTENT_KIND = "taskvector-tool-config"
PRIORITY = 100


def matches(path: Path, data: object = None) -> bool:
    p = path.as_posix().lower()
    return ("agents/tools/" in p) and path.suffix.lower() == ".yaml"
