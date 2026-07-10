"""
Saves the current workflow graph as a *versioned* JSON file.

Path is defined by a template stored in Settings, with placeholders:
  - $PROJECT_NAME$
  - $YY-MM-DD-HHMMSS$

Each save writes a new timestamped file *only if the graph changed* compared to the latest saved version.
Change detection uses an MD5 hash of the canonical JSON.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Union


from core.schemas.process_graph import ProcessGraph
from gui.components.settings import (
    REPO_ROOT,
    get_workflow_project_name,
    get_workflow_save_path_template,
)

PLACEHOLDER_PROJECT_NAME = "$PROJECT_NAME$"
PLACEHOLDER_TIMESTAMP = "$YY-MM-DD-HHMMSS$"


def _now_timestamp() -> str:
    """Timestamp in YY-MM-DD-HHMMSS format."""
    return datetime.now().strftime("%y-%m-%d-%H%M%S")


def resolve_workflow_save_path(
    template: str, *, project_name: str, timestamp: str
) -> str:
    """Apply placeholder substitution and return the resolved path string."""
    return (
        (template or "")
        .replace(PLACEHOLDER_PROJECT_NAME, project_name)
        .replace(PLACEHOLDER_TIMESTAMP, timestamp)
    )


def _graph_to_payload(graph: Optional[Union[ProcessGraph, dict]]) -> dict:
    """Normalize to a full dict for saving. Handles ProcessGraph or dict (e.g. from workflow); ensures all keys."""
    if graph is None:
        return {"environment_type": "thermodynamic", "units": [], "connections": []}
    if isinstance(graph, dict):
        try:
            validated = ProcessGraph.model_validate(graph)
            return validated.model_dump(by_alias=True)
        except Exception:
            return dict(graph)
    # graph is a ProcessGraph instance
    return graph.model_dump(by_alias=True)


def _graph_json_bytes(graph: Optional[Union[ProcessGraph, dict]]) -> bytes:
    """
    Stable bytes for hashing/saving.
    Uses canonical key order (units, connections first) so the file is readable and no data is dropped.
    """
    payload = _graph_to_payload(graph)
    # Canonical order: units and connections first, then rest (stable for all origins/runtimes).
    order = (
        "environment_type",
        "environments",
        "units",
        "connections",
        "code_blocks",
        "layout",
        "origin",
        "origin_format",
        "runtime",
        "tabs",
        "metadata",
        "comments",
        "todo_lists",
    )
    ordered = {k: payload[k] for k in order if k in payload}
    for k, v in payload.items():
        if k not in ordered:
            ordered[k] = v
    s = json.dumps(ordered, indent=2, sort_keys=False)
    return s.encode("utf-8")


def _md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _latest_saved_json(project_dir: Path) -> Optional[Path]:
    """Return the lexicographically-latest JSON file in project_dir, or None."""
    if not project_dir.exists() or not project_dir.is_dir():
        return None
    files = sorted([p for p in project_dir.glob("*.json") if p.is_file()])
    return files[-1] if files else None


@dataclass(frozen=True)
class SaveResult:
    saved: bool
    path: Optional[Path]
    reason: str  # "saved" | "no_changes" | "no_graph" | "error"


def save_workflow_version(
    graph: Optional[Union[ProcessGraph, dict]],
    *,
    project_name: Optional[str] = None,
    template: Optional[str] = None,
) -> SaveResult:
    """
    Save a new timestamped workflow JSON version (if graph differs from latest).
    Returns SaveResult with status and saved path (if saved).
    """
    if graph is None:
        return SaveResult(saved=False, path=None, reason="no_graph")

    project_name = (project_name or get_workflow_project_name()).strip() or "my_project"
    template = (template or get_workflow_save_path_template()).strip()
    if not template:
        return SaveResult(saved=False, path=None, reason="error")

    ts = _now_timestamp()
    rel = resolve_workflow_save_path(
        template, project_name=project_name, timestamp=ts
    ).strip()
    path = (REPO_ROOT / rel) if not Path(rel).is_absolute() else Path(rel)
    project_dir = path.parent

    try:
        data = _graph_json_bytes(graph)
        cur_hash = _md5_hex(data)

        latest = _latest_saved_json(project_dir)
        if latest is not None:
            latest_bytes = latest.read_bytes()
            if _md5_hex(latest_bytes) == cur_hash:
                return SaveResult(saved=False, path=latest, reason="no_changes")

        project_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return SaveResult(saved=True, path=path, reason="saved")
    except OSError:
        return SaveResult(saved=False, path=path, reason="error")
