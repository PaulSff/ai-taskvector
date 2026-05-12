"""TaskVector process graph: ``units`` + ``connections`` lists (unit id/type shape)."""

from __future__ import annotations

from pathlib import Path

CONTENT_KIND = "canonical"
PRIORITY = 30


def matches(path: Path, data: dict | list) -> bool:
    del path
    if not isinstance(data, dict):
        return False
    units = data.get("units")
    connections = data.get("connections")
    if not isinstance(units, list) or not isinstance(connections, list):
        return False
    if len(units) == 0:
        return True
    first = units[0]
    return isinstance(first, dict) and "id" in first and "type" in first
