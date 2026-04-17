"""Node-RED flow JSON: tab/nodes list, ``flows``, or library ``flow`` wrapper."""
from __future__ import annotations

from pathlib import Path
from typing import Any

JSON_KIND = "node_red"
PRIORITY = 40


def _looks_like_node_red_flow(data: dict | list) -> bool:
    if isinstance(data, list):
        return len(data) > 0 and isinstance(data[0], dict) and ("type" in data[0] or "id" in data[0])
    if isinstance(data, dict):
        if "nodes" in data or "flows" in data:
            return True
        if "flow" in data and isinstance(data.get("flow"), list) and len(data["flow"]) > 0:
            first = data["flow"][0]
            if isinstance(first, dict) and ("type" in first or "id" in first):
                return True
    return False


def matches(path: Path, data: dict | list) -> bool:
    del path
    return _looks_like_node_red_flow(data)
