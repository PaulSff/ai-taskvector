"""
Resolve import_unit and import_workflow edits to concrete add_unit / replace_graph edits.
Import edits reference RAG-indexed nodes or workflows; resolution loads the data
and produces edits that apply_graph_edit can handle.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from normalizer.normalizer import FormatProcess, to_process_graph


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


def resolve_import_unit(
    edit: dict[str, Any],
    rag_index_dir: str | Path,
    current: dict[str, Any],
    rag_embedding_model: str | None = None,
) -> list[dict[str, Any]]:
    """
    Resolve import_unit to add_unit edit.
    Returns list of one add_unit edit, or empty list on failure.
    """
    node_id = edit.get("node_id") or edit.get("id")
    if not node_id:
        return []
    try:
        from rag.indexer import RAGIndex

        index = RAGIndex(persist_dir=str(rag_index_dir), embedding_model=rag_embedding_model)
        meta = index.get_node_by_id(str(node_id))
        if not meta:
            return []
        node_types = meta.get("node_types") or meta.get("node_type")
        if isinstance(node_types, str):
            node_types = [node_types]
        if not isinstance(node_types, list) or not node_types:
            return []
        unit_type = str(node_types[0]).strip() or "Unit"
        target_id = edit.get("unit_id")
        if not target_id:
            existing = {u.get("id") for u in (current.get("units") or []) if isinstance(u, dict) and u.get("id")}
            target_id = _generate_unit_id(node_types, existing)
        return [
            {
                "action": "add_unit",
                "unit": {
                    "id": target_id,
                    "type": unit_type,
                    "controllable": False,
                    "params": {},
                },
            }
        ]
    except Exception:
        return []


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


def _load_workflow_source(source: str) -> tuple[dict | list, FormatProcess] | None:
    """Load workflow JSON from file path or URL. Returns (raw_data, format) or None."""
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
    fmt = _detect_workflow_format(raw)
    return (raw, fmt)


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
    """
    source = edit.get("source")
    if not source:
        return []
    loaded = _load_workflow_source(source)
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
    *,
    rag_index_dir: str | Path | None = None,
    rag_embedding_model: str | None = None,
) -> list[dict[str, Any]]:
    """
    Resolve import_unit and import_workflow edits to concrete edits.
    Other edits are passed through unchanged.
    """
    resolved: list[dict[str, Any]] = []
    for edit in edits:
        if not isinstance(edit, dict):
            continue
        action = edit.get("action")
        if action == "import_unit":
            if rag_index_dir:
                sub = resolve_import_unit(edit, rag_index_dir, current, rag_embedding_model)
                resolved.extend(sub)
            # else skip (no RAG index configured)
        elif action == "import_workflow":
            sub = resolve_import_workflow(edit, current)
            resolved.extend(sub)
        else:
            resolved.append(edit)
    return resolved
