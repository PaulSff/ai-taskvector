"""
Extract searchable metadata from workflows (Node-RED, n8n) and node catalogues.
Accepts both string and parsed JSON (list/dict) for text fields (description, name, label, etc.).

Classification of JSON (workflow vs catalogue vs library) is in rag.discriminant.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _to_string(val: Any) -> str:
    """Normalize to string: keep str, convert list/dict to JSON string, else str()."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (list, dict)):
        try:
            return json.dumps(val, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(val)
    return str(val)


def _to_string_list(val: Any) -> list[str]:
    """Normalize to list of strings (e.g. keywords, categories). Accepts list, single str, or dict/other."""
    if val is None:
        return []
    if isinstance(val, list):
        return [_to_string(x) for x in val if x is not None]
    if isinstance(val, str):
        return [val] if val.strip() else []
    return [_to_string(val)]


def extract_node_red_workflow_meta(raw: dict | list, source: str) -> dict[str, Any]:
    """Extract metadata from Node-RED flow JSON for indexing."""
    nodes: list[dict] = []
    if isinstance(raw, list):
        nodes = raw
    elif isinstance(raw, dict):
        nodes = raw.get("nodes") or []
        flows = raw.get("flows")
        if flows and isinstance(flows, list) and flows:
            first = flows[0]
            if isinstance(first, dict) and "nodes" in first:
                nodes = first["nodes"]
            elif isinstance(first, list):
                nodes = first

    unit_types: set[str] = set()
    labels: list[str] = []
    name = "Unknown"
    for n in nodes:
        if not isinstance(n, dict):
            continue
        ntype = (n.get("type") or n.get("unitType") or n.get("processType") or "")
        if str(ntype).lower() == "tab":
            name = _to_string(n.get("label") or n.get("name") or name)
        if ntype:
            unit_types.add(str(ntype).split(".")[-1])
        lbl = n.get("label") or n.get("name")
        if lbl is not None and str(ntype).lower() != "tab":
            labels.append(_to_string(lbl))

    if isinstance(raw, dict) and name == "Unknown":
        tab = raw.get("flows", [{}])[0] if raw.get("flows") else raw
        if isinstance(tab, dict):
            name = _to_string(tab.get("label") or tab.get("name") or name)

    return {
        "content_type": "workflow",
        "format": "node_red",
        "name": name,
        "source": source,
        "unit_types": list(unit_types),
        "labels": labels[:20],
        "node_count": len([n for n in nodes if isinstance(n, dict) and n.get("type")]),
    }


def extract_n8n_workflow_meta(raw: dict, source: str) -> dict[str, Any]:
    """Extract metadata from n8n workflow JSON for indexing."""
    nodes = raw.get("nodes") or []
    integrations: set[str] = set()
    labels: list[str] = []

    for n in nodes:
        if not isinstance(n, dict):
            continue
        ntype = n.get("type") or ""
        if isinstance(ntype, str) and "." in ntype:
            integrations.add(ntype.split(".")[-1])
        name = n.get("name")
        if name is not None:
            labels.append(_to_string(name))

    wf_name = _to_string(raw.get("name") or "Unknown")
    if isinstance(raw.get("meta"), dict):
        wf_name = _to_string(raw["meta"].get("instanceId") or wf_name)

    return {
        "content_type": "workflow",
        "format": "n8n",
        "name": wf_name,
        "source": source,
        "integrations": list(integrations),
        "labels": labels[:20],
        "node_count": len(nodes),
    }


def extract_canonical_workflow_meta(raw: dict, source: str) -> dict[str, Any]:
    """Extract metadata from canonical process graph JSON (ProcessGraph: units + connections) for indexing."""
    units = raw.get("units") or []
    unit_types: set[str] = set()
    labels: list[str] = []
    for u in units:
        if not isinstance(u, dict):
            continue
        utype = (u.get("type") or "").strip()
        if utype:
            unit_types.add(utype)
        uid = u.get("id")
        if uid is not None:
            labels.append(_to_string(uid))
    name = _to_string(raw.get("name") or "Canonical graph")
    return {
        "content_type": "workflow",
        "format": "canonical",
        "name": name,
        "source": source,
        "unit_types": list(unit_types),
        "labels": labels[:20],
        "node_count": len(units),
    }


def workflow_meta_to_text(meta: dict[str, Any]) -> str:
    """Convert workflow metadata to searchable text for embedding."""
    parts = [f"Workflow: {meta.get('name', '')}"]
    if meta.get("unit_types"):
        parts.append(f"Node types: {', '.join(meta['unit_types'])}")
    if meta.get("integrations"):
        parts.append(f"Integrations: {', '.join(meta['integrations'])}")
    if meta.get("labels"):
        parts.append(f"Nodes: {', '.join(meta['labels'][:10])}")
    parts.append(f"Format: {meta.get('format', '')}")
    return " | ".join(parts)


def extract_node_red_catalogue_module(module: dict, source: str = "node_red_catalogue") -> dict[str, Any]:
    """Extract metadata from one Node-RED catalogue module (npm package). description/keywords/etc. can be string or parsed JSON."""
    mid = _to_string(module.get("id") or "")
    desc = _to_string(module.get("description") or "")
    keywords = _to_string_list(module.get("keywords"))
    types_list = _to_string_list(module.get("types"))[:30]
    categories = _to_string_list(module.get("categories"))
    url = _to_string(module.get("url") or "")

    return {
        "content_type": "node",
        "format": "node_red",
        "id": mid,
        "name": mid,
        "source": source,
        "description": desc,
        "keywords": keywords,
        "node_types": types_list,
        "categories": categories,
        "url": url,
    }


def node_meta_to_text(meta: dict[str, Any]) -> str:
    """Convert node metadata to searchable text for embedding."""
    parts = [
        meta.get("name", ""),
        meta.get("description", ""),
        " ".join(meta.get("keywords", [])),
        " ".join(meta.get("categories", [])),
        " ".join(meta.get("node_types", [])[:15]),
    ]
    return " | ".join(p for p in parts if p)


def extract_node_red_library_entry(entry: dict, source: str, entry_id: str = "") -> dict[str, Any]:
    """Extract metadata from one Node-RED library flow entry (from flows-refined or library JSON)."""
    readme = _to_string(entry.get("readme") or "")
    summary = _to_string(entry.get("summary") or "")
    name = summary.strip() or readme[:80].strip() or entry_id or "Unknown"
    if len(name) > 200:
        name = name[:197] + "..."
    return {
        "content_type": "flow_library",
        "format": "node_red",
        "name": name,
        "source": source,
        "id": entry_id,
        "readme": readme[:2000],
        "summary": summary[:500],
    }


def library_entry_meta_to_text(meta: dict[str, Any]) -> str:
    """Convert library flow entry metadata to searchable text for embedding."""
    parts = [
        f"Flow: {meta.get('name', '')}",
        meta.get("summary", ""),
        (meta.get("readme") or "")[:500],
    ]
    return " | ".join(p for p in parts if p)


def load_workflow_json(path: Path) -> dict | list | None:
    """Load workflow JSON from file. Classify with rag.discriminant.classify_json_for_rag after load."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(text)
    except Exception:
        return None

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "nodes" in data and "connections" in data:
            return data  # n8n
        if "nodes" in data or "flows" in data or any(
            isinstance(v, list) and v and isinstance(v[0], dict)
            for v in (data.get("flows"), data.get("nodes"))
        ):
            return data  # Node-RED
    return data
