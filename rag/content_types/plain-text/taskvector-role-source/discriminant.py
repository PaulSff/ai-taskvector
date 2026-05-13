from __future__ import annotations

from pathlib import Path

CONTENT_KIND = "taskvector-role-source"
PRIORITY = 100


def matches(path: Path, data: object = None) -> bool:
    p = path.as_posix().lower()
    return ("assistants/roles/" in p) and path.suffix.lower() == ".py"
