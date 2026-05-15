"""
Resolve import_workflow edits to concrete replace_graph (or merge) edits.
import_workflow loads from file path or URL; resolution produces edits that apply_graph_edit can handle.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

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


_VALID_ORIGIN: set[str] = {
    "node_red",
    "n8n",
    "dict",
    "canonical",
    "yaml",
    "template",
    "pyflow",
    "ryven",
    "idaes",
    "comfyui",
}


def _load_workflow_source(
    source: str, origin: str | None = None
) -> tuple[dict | list, FormatProcess] | None:
    source = (source or "").strip()
    if not source:
        return None

    # Load raw data
    if source.startswith(("http://", "https://")):
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

    # Use provided origin if valid
    if origin and (fmt_raw := str(origin).strip().lower()) in _VALID_ORIGIN:
        if fmt_raw == "canonical":
            fmt_raw = "dict"
        return (raw, cast(FormatProcess, fmt_raw))

    # Otherwise detect
    fmt = _detect_workflow_format(raw)
    # Ensure _detect_workflow_format returns FormatProcess
    return (raw, fmt)


def load_workflow_to_canonical(
    source: str, origin: str | None = None
) -> tuple[dict | None, str]:
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
        out = (
            graph.model_dump(by_alias=True)
            if hasattr(graph, "model_dump")
            else dict(graph)
        )
        return (out, "")
    except Exception as e:
        return (None, str(e))


def _graph_dict_to_edit_format(
    graph: Any, origin_format: str | None = None
) -> dict[str, Any]:
    """Convert ProcessGraph or dict to replace_graph edit format. Carries origin_format, runtime, origin, metadata, comments so apply preserves import."""
    if hasattr(graph, "model_dump"):
        d = graph.model_dump(by_alias=True)
    else:
        d = dict(graph)
    units = []
    for u in d.get("units") or []:
        if isinstance(u, dict):
            units.append(
                {
                    "id": str(u.get("id", "")),
                    "type": str(u.get("type", "Unit")),
                    "controllable": bool(u.get("controllable", False)),
                    "params": dict(u.get("params", {})),
                }
            )
    connections = []
    for c in d.get("connections") or []:
        if isinstance(c, dict):
            fr = c.get("from") or c.get("from_id")
            to = c.get("to") or c.get("to_id")
            if fr is not None and to is not None:
                connections.append({"from": str(fr), "to": str(to)})
    out: dict[str, Any] = {
        "action": "replace_graph",
        "units": units,
        "connections": connections,
    }
    fmt = origin_format or d.get("origin_format")
    if isinstance(fmt, str) and fmt.strip():
        out["origin_format"] = fmt.strip()
    if d.get("runtime") is not None:
        out["runtime"] = d.get("runtime")
    if d.get("origin") is not None:
        out["origin"] = d["origin"]
    if d.get("metadata") is not None and isinstance(d.get("metadata"), dict):
        out["metadata"] = dict(d["metadata"])
    if d.get("comments") is not None and isinstance(d.get("comments"), list):
        out["comments"] = list(d["comments"])
    if d.get("code_blocks") is not None and isinstance(d.get("code_blocks"), list):
        out["code_blocks"] = [
            dict(cb) for cb in d["code_blocks"] if isinstance(cb, dict) and cb.get("id")
        ]
    if d.get("layout") is not None and isinstance(d.get("layout"), dict):
        out["layout"] = dict(d["layout"])
    return out


def resolve_import_workflow(
    edit: dict[str, Any],
    current: dict[str, Any],
) -> list[dict[str, Any]]:
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

    edit_payload = _graph_dict_to_edit_format(graph, origin_format=fmt)

    if edit.get("merge"):
        # Sanitize current units: collect only dict units with string IDs
        curr_units = current.get("units") or []
        existing_ids: set[str] = set()
        for u in curr_units:
            if isinstance(u, dict):
                uid = u.get("id")
                if isinstance(uid, str):
                    existing_ids.add(uid)
                # else: ignore non-string/missing IDs

        id_map: dict[str, str] = {}
        new_units = list(edit_payload.get("units") or [])
        for u in new_units:
            # Get ID safely: only if it's a string, otherwise generate fresh
            old_id = u.get("id")
            if not isinstance(old_id, str):
                # Fallback: generate ID on the fly if missing/invalid
                old_id = ""

            # Check if old_id exists in current or in already-generated IDs
            if old_id in existing_ids or old_id in id_map.values():
                # Generate new ID using only valid existing IDs
                fresh_id = _generate_unit_id(
                    [u.get("type", "unit") or "unit"],  # ensure type is str | fallback
                    existing_ids | set(id_map.values()),  # now safe: both are set[str]
                )
                id_map[old_id] = fresh_id
                u["id"] = fresh_id
                existing_ids.add(fresh_id)
            else:
                if old_id:  # only add if non-empty
                    existing_ids.add(old_id)

        # Rebuild connections safely
        new_conns = []
        curr_conns = []
        for c in current.get("connections") or []:
            if isinstance(c, dict):
                fr = c.get("from") or c.get("from_id")
                to = c.get("to") or c.get("to_id")
                if isinstance(fr, str) and isinstance(to, str):
                    curr_conns.append({"from": fr, "to": to})

        for c in edit_payload.get("connections") or []:
            if not isinstance(c, dict):
                continue
            fr = c.get("from")
            to = c.get("to")
            if not isinstance(fr, str) or not isinstance(to, str):
                continue
            # Resolve remapped IDs
            fr = id_map.get(fr, fr)
            to = id_map.get(to, to)
            # Ensure both are now strings and in existing_ids (after remap)
            if fr in existing_ids and to in existing_ids:
                new_conns.append({"from": fr, "to": to})

        # Final merge
        final_units = curr_units + new_units
        final_conns = curr_conns + new_conns
        return [
            {
                "action": "replace_graph",
                "units": final_units,
                "connections": final_conns,
            }
        ]

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
