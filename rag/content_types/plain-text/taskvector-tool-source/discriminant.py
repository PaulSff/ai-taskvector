from __future__ import annotations

from pathlib import Path

CONTENT_KIND = "taskvector-tool-source"
PRIORITY = 100


def matches(path: Path, data: object = None) -> bool:
    p = path.as_posix().lower()
    return ("assistants/tools/" in p) and path.suffix.lower() == ".py"
