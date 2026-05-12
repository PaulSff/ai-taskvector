"""n8n workflow JSON: ``nodes`` (list) and ``connections`` (object)."""

from __future__ import annotations

from pathlib import Path

CONTENT_KIND = "n8n"
PRIORITY = 10


def matches(path: Path, data: dict | list) -> bool:
    del path
    if not isinstance(data, dict):
        return False
    return isinstance(data.get("nodes"), list) and isinstance(
        data.get("connections"), dict
    )
