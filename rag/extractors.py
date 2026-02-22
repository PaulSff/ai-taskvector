"""
Extract searchable metadata from workflows (Node-RED, n8n) and node catalogues.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
            name = n.get("label") or n.get("name") or name
        if ntype:
            unit_types.add(str(ntype).split(".")[-1])
        lbl = n.get("label") or n.get("name")
        if lbl and isinstance(lbl, str) and str(ntype).lower() != "tab":
            labels.append(lbl)

    if isinstance(raw, dict) and name == "Unknown":
        tab = raw.get("flows", [{}])[0] if raw.get("flows") else raw
        if isinstance(tab, dict):
            name = tab.get("label") or tab.get("name") or name

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
        if name and isinstance(name, str):
            labels.append(name)

    wf_name = raw.get("name") or "Unknown"
    if isinstance(raw.get("meta"), dict):
        wf_name = raw["meta"].get("instanceId") or wf_name

    return {
        "content_type": "workflow",
        "format": "n8n",
        "name": wf_name,
        "source": source,
        "integrations": list(integrations),
        "labels": labels[:20],
        "node_count": len(nodes),
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
    """Extract metadata from one Node-RED catalogue module (npm package)."""
    mid = module.get("id") or ""
    desc = module.get("description") or ""
    keywords = module.get("keywords") or []
    types_list = module.get("types") or []
    categories = module.get("categories") or []
    url = module.get("url") or ""

    return {
        "content_type": "node",
        "format": "node_red",
        "id": mid,
        "name": mid,
        "source": source,
        "description": desc,
        "keywords": keywords if isinstance(keywords, list) else [],
        "node_types": types_list[:30] if isinstance(types_list, list) else [],
        "categories": categories if isinstance(categories, list) else [],
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


def load_workflow_json(path: Path) -> dict | list | None:
    """Load workflow JSON from file; detect Node-RED vs n8n by structure."""
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
