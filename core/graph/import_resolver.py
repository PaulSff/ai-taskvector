"""
Resolve import_workflow edits to concrete replace_graph (or merge) edits.
import_workflow loads from file path or URL; resolution produces edits that apply_graph_edit can handle.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.graph.graph_edits import PIPELINE_TYPES
from core.normalizer.normalizer import FormatProcess, to_process_graph


def _slug_from_type(node_type: str) -> str:
    """Convert node type to a safe id slug (e.g. 'http request' -> 'http_request')."""
    s = re.sub(r"[^a-zA-Z0-9]+", "_", str(node_type).strip())
    return (s or "unit").strip("_").lower()


def _generate_unit_id(node_types: list[str], existing_ids: set[str]) -> str:
    """Generate a unique unit id from node type."""
    base = _slug_from_type(node_types[0]) if node_types else "unit"
    for i in range(1, 1000):
        candidate = f"{base}_{i}" if i > 1 else base
        if candidate not in existing_ids:
            return candidate
    return f"{base}_{hash(str(existing_ids)) % 10000}"


def _detect_workflow_format(raw: dict | list) -> FormatProcess:
    """Detect workflow format from raw JSON structure."""
    if isinstance(raw, dict):
        if "nodes" in raw and "links" in raw and raw.get("version") is not None:
            return "comfyui"
        if "nodes" in raw and "connections" in raw:
            return "n8n"
        if "nodes" in raw or "flows" in raw:
            return "node_red"
    if isinstance(raw, list):
        return "node_red"
    return "node_red"


_VALID_ORIGIN: set[str] = {"node_red", "n8n", "dict", "canonical", "yaml", "template", "pyflow", "ryven", "idaes", "comfyui"}


def _load_workflow_source(source: str, origin: str | None = None) -> tuple[dict | list, FormatProcess] | None:
    """Load workflow JSON from file path or URL. Returns (raw_data, format) or None.
    If origin is provided and valid (e.g. node_red, n8n), use it as format; else detect from raw structure.
    """
    source = (source or "").strip()
    if not source:
        return None
    if source.startswith("http://") or source.startswith("https://"):
        try:
            import requests

            r = requests.get(source, timeout=60)
            r.raise_for_status()
            raw = r.json()
        except Exception:
            return None
    else:
        path = Path(source).expanduser().resolve()
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return None
    if origin and str(origin).strip().lower() in _VALID_ORIGIN:
        fmt = origin.strip().lower()
        if fmt == "canonical":
            fmt = "dict"
        return (raw, fmt)
    fmt = _detect_workflow_format(raw)
    return (raw, fmt)


def load_workflow_to_canonical(source: str, origin: str | None = None) -> tuple[dict | None, str]:
    """
    Load workflow from file path or URL and convert to canonical graph dict.
    Returns (canonical_dict, error_msg). On success error_msg is empty; on failure canonical_dict is None.
    """
    if not (source and str(source).strip()):
        return (None, "source is empty")
    loaded = _load_workflow_source(str(source).strip(), origin=origin)
    if not loaded:
        return (None, "failed to load source (file not found or invalid)")
    raw, fmt = loaded
    try:
        graph = to_process_graph(raw, format=fmt)
        out = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else dict(graph)
        return (out, "")
    except Exception as e:
        return (None, str(e))


def _graph_dict_to_edit_format(graph: Any) -> dict[str, Any]:
    """Convert ProcessGraph or dict to replace_graph edit format."""
    if hasattr(graph, "model_dump"):
        d = graph.model_dump(by_alias=True)
    else:
        d = dict(graph)
    units = []
    for u in d.get("units") or []:
        if isinstance(u, dict):
            units.append({
                "id": str(u.get("id", "")),
                "type": str(u.get("type", "Unit")),
                "controllable": bool(u.get("controllable", False)),
                "params": dict(u.get("params", {})),
            })
    connections = []
    for c in d.get("connections") or []:
        if isinstance(c, dict):
            fr = c.get("from") or c.get("from_id")
            to = c.get("to") or c.get("to_id")
            if fr is not None and to is not None:
                connections.append({"from": str(fr), "to": str(to)})
    return {"action": "replace_graph", "units": units, "connections": connections}


def resolve_import_workflow(
    edit: dict[str, Any],
    current: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Resolve import_workflow to replace_graph (or merge) edit.
    Returns list of edits.
    Optional edit["origin"]: "node_red" | "n8n" | "dict" | etc. to force the normalizer format (avoids misdetection).
    """
    source = edit.get("source")
    if not source:
        return []
    origin = edit.get("origin") or edit.get("format")
    loaded = _load_workflow_source(source, origin=origin)
    if not loaded:
        return []
    raw, fmt = loaded
    try:
        graph = to_process_graph(raw, format=fmt)
    except Exception:
        return []
    edit_payload = _graph_dict_to_edit_format(graph)
    if edit.get("merge"):
        # Merge: append units and connections, disambiguate ids
        existing_ids = {u.get("id") for u in (current.get("units") or []) if isinstance(u, dict)}
        id_map: dict[str, str] = {}
        new_units = list(edit_payload.get("units") or [])
        for u in new_units:
            old_id = u.get("id", "")
            if old_id in existing_ids or old_id in id_map.values():
                new_id = _generate_unit_id([u.get("type", "unit")], existing_ids | set(id_map.values()))
                id_map[old_id] = new_id
                u["id"] = new_id
                existing_ids.add(new_id)
            else:
                existing_ids.add(old_id)
        new_conns = []
        for c in edit_payload.get("connections") or []:
            fr = c.get("from", "")
            to = c.get("to", "")
            fr = id_map.get(fr, fr)
            to = id_map.get(to, to)
            if fr in existing_ids and to in existing_ids:
                new_conns.append({"from": fr, "to": to})
        curr_units = list(current.get("units") or [])
        curr_conns = [{"from": c.get("from") or c.get("from_id"), "to": c.get("to") or c.get("to_id")} for c in (current.get("connections") or []) if isinstance(c, dict)]
        curr_units.extend(new_units)
        curr_conns.extend(new_conns)
        return [{"action": "replace_graph", "units": curr_units, "connections": curr_conns}]
    return [edit_payload]


def resolve_import_edits(
    edits: list[dict[str, Any]],
    current: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Resolve import_workflow edits to concrete replace_graph (or merge) edits.
    Other edits are passed through unchanged.
    """
    resolved: list[dict[str, Any]] = []
    for edit in edits:
        if not isinstance(edit, dict):
            continue
        action = edit.get("action")
        if action == "import_workflow":
            sub = resolve_import_workflow(edit, current)
            resolved.extend(sub)
        else:
            resolved.append(edit)
    return resolved
