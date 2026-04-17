"""Node-RED palette catalogue: top-level ``modules`` list of dicts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

JSON_KIND = "node_red_catalogue"
PRIORITY = 20


def matches(path: Path, data: dict | list) -> bool:
    del path
    if not isinstance(data, dict):
        return False
    mods = data.get("modules")
    return isinstance(mods, list) and len(mods) > 0 and isinstance(mods[0], dict)
