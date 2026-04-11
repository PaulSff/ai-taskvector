"""Resolve workflow JSON paths from ``assistants/tools/<tool_id>/tool.yaml`` ``workflow`` field."""
from __future__ import annotations

from pathlib import Path

import yaml

_TOOLS_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _TOOLS_ROOT.parent.parent


def get_tool_workflow_path(tool_id: str) -> Path:
    """
    Return absolute path to the workflow JSON for this tool.

    - Reads ``workflow`` from ``assistants/tools/<tool_id>/tool.yaml``.
    - If relative and starts with ``assistants/``, ``gui/``, or ``config/``: resolve from repo root.
    - If relative otherwise: resolve under ``assistants/tools/<tool_id>/``.
    - If absolute: use as-is.
    """
    key = (tool_id or "").strip()
    if not key:
        raise ValueError("tool_id is required")
    meta = _TOOLS_ROOT / key / "tool.yaml"
    if not meta.is_file():
        raise FileNotFoundError(f"tool.yaml not found for tool {key!r}: {meta}")
    data = yaml.safe_load(meta.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"tool.yaml for {key!r} must be a mapping")
    raw = str(data.get("workflow") or "").strip()
    if not raw:
        raise ValueError(f"tool.yaml for {key!r} must set ``workflow`` (workflow JSON path).")
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p.resolve()
    norm = str(p).replace("\\", "/")
    if norm.startswith(("assistants/", "gui/", "config/")):
        return (_REPO_ROOT / p).resolve()
    return (_TOOLS_ROOT / key / p).resolve()
