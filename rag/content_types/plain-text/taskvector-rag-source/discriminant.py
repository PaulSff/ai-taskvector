from __future__ import annotations

from pathlib import Path

CONTENT_KIND = "taskvector-rag-readme"
PRIORITY = 1


def _is_one_level_below_rag(path: Path) -> bool:
    # Normalize to posix and strip leading slash
    parts = [p for p in path.as_posix().lstrip("/").split("/") if p]
    # find any "rag" in the path and ensure there is exactly one segment after it,
    # e.g. ".../rag/readme.md" -> True; ".../rag/tools/readme.md" -> False
    for i, seg in enumerate(parts):
        if seg == "rag":
            # require one more segment and that it is the file (no further subdirs)
            return (i + 1 == len(parts) - 0) and (len(parts) >= i + 2)
    return False


def matches(path: Path, data: object = None) -> bool:
    try:
        if path.suffix.lower() != ".py":
            return False
        return _is_one_level_below_rag(path)
    except Exception:
        return False
