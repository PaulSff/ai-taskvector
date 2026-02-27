"""
Extract searchable metadata from workflows (Node-RED, n8n) and node catalogues.
Accepts both string and parsed JSON (list/dict) for text fields (description, name, label, etc.).

JSON classification (how .json in mydata is interpreted)
--------------------------------------------------------
Currently classification is structure-only unless path-based rules apply (see classify_json_for_rag).

Structure-only rules (used when path does not hint type):
  - dict with "nodes" AND "connections" → n8n workflow
  - everything else (list, or dict with "nodes"/"flows") → Node-RED workflow extractor

Misclassification examples:
  - Catalogue JSON ({"modules": [...]}) → sent to Node-RED workflow extractor → nodes=[],
    name="Unknown", almost empty searchable text.
  - Library flows JSON ([{"_id", "flow", "readme", "summary", ...}]) → list treated as
    list of nodes → "nodes" become full library entries, type/label wrong.
  - Arbitrary config with "nodes" key (e.g. list of server names) → treated as workflow.
  - n8n workflow missing "connections" key → treated as Node-RED.

Recommended mydata structure (path-based rules):
  - mydata/node-red/nodes/                    → Node-RED nodes; catalogue (modules) lives here
  - mydata/node-red/nodes/catalogue.json      → Node-RED catalogue (modules)
  - mydata/node-red/workflows/                → Node-RED workflows; single flow or library
  - mydata/node-red/workflows/node-red-library-flows-refined.json  → library (list of entries)
  - mydata/n8n/workflows/                     → n8n workflows
  - mydata/n8n/nodes/                         → n8n nodes (rules TBD)
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


def _path_parts_lower(path: Path) -> list[str]:
    """Normalized path parts (lowercase) for path-based classification."""
    return [p.lower() for p in path.parts]


def _looks_like_n8n(data: dict) -> bool:
    """Structure heuristic: n8n workflow has nodes and connections."""
    return isinstance(data.get("nodes"), list) and isinstance(data.get("connections"), dict)


def _looks_like_node_red_catalogue(data: dict) -> bool:
    """Structure heuristic: Node-RED catalogue has top-level 'modules' list."""
    mods = data.get("modules")
    return isinstance(mods, list) and len(mods) > 0 and isinstance(mods[0], dict)


def _looks_like_node_red_library_flows(data: list) -> bool:
    """Structure heuristic: library flows = list of dicts with _id, flow, readme/summary."""
    if not isinstance(data, list) or len(data) == 0:
        return False
    first = data[0]
    return isinstance(first, dict) and ("_id" in first or "id" in first) and ("flow" in first or "readme" in first)


def _looks_like_node_red_flow(data: dict | list) -> bool:
    """Structure heuristic: Node-RED flow = list of nodes or dict with nodes/flows."""
    if isinstance(data, list):
        return len(data) > 0 and isinstance(data[0], dict) and ("type" in data[0] or "id" in data[0])
    if isinstance(data, dict):
        if "nodes" in data or "flows" in data:
            return True
    return False


def classify_json_for_rag(path: Path, data: dict | list | None) -> str:
    """
    Classify JSON for RAG extraction. Returns one of:
    "n8n" | "n8n_nodes" | "node_red" | "node_red_catalogue" | "node_red_library" | "node_red_nodes" | "generic"

    Path-based rules (mydata structure) take precedence:
      mydata/n8n/workflows/     → n8n
      mydata/n8n/nodes/        → n8n_nodes (rules TBD; indexer skips or generic)
      mydata/node-red/nodes/   → if data has "modules" (catalogue) → node_red_catalogue, else node_red_nodes
      mydata/node-red/workflows/  → if data looks like library list → node_red_library, else node_red
    Then structure heuristics as fallback.
    """
    if data is None:
        return "generic"
    path_parts = _path_parts_lower(path)
    path_str = path.as_posix().lower()

    # --- n8n: workflows vs nodes ---
    if "n8n" in path_parts:
        if "workflows" in path_parts:
            if isinstance(data, dict) and _looks_like_n8n(data):
                return "n8n"
            if isinstance(data, dict):
                return "n8n"
        if "nodes" in path_parts:
            return "n8n_nodes"  # rules TBD; indexer treats as generic/skip
        # n8n elsewhere (e.g. mydata/n8n/) → treat as workflow if structure fits
        if isinstance(data, dict) and _looks_like_n8n(data):
            return "n8n"
        if isinstance(data, dict):
            return "n8n"

    # --- node-red: nodes (catalogue or other), workflows (single or library) ---
    if "node-red" in path_parts or "nodered" in path_str:
        if "nodes" in path_parts:
            # Catalogue (modules) lives under node-red/nodes/; other node JSON TBD
            if isinstance(data, dict) and _looks_like_node_red_catalogue(data):
                return "node_red_catalogue"
            return "node_red_nodes"  # rules TBD; indexer skips
        if "workflows" in path_parts:
            # Library = list of {_id, flow, readme, summary}; single flow = dict or list of nodes
            if isinstance(data, list) and _looks_like_node_red_library_flows(data):
                return "node_red_library"
            if isinstance(data, list):
                return "node_red_library"
            if isinstance(data, dict) and _looks_like_node_red_flow(data):
                return "node_red"
            if isinstance(data, dict):
                return "node_red"
            if isinstance(data, list) and _looks_like_node_red_flow(data):
                return "node_red"
            return "node_red"
        # node-red elsewhere → workflow or catalogue by structure
        if isinstance(data, dict) and _looks_like_node_red_catalogue(data):
            return "node_red_catalogue"
        if isinstance(data, list) and _looks_like_node_red_library_flows(data):
            return "node_red_library"
        return "node_red"

    # --- Structure fallback (no path hint) ---
    if isinstance(data, dict):
        if _looks_like_n8n(data):
            return "n8n"
        if _looks_like_node_red_catalogue(data):
            return "node_red_catalogue"
        if _looks_like_node_red_flow(data):
            return "node_red"
    if isinstance(data, list):
        if _looks_like_node_red_library_flows(data):
            return "node_red_library"
        if _looks_like_node_red_flow(data):
            return "node_red"
    return "generic"


def load_workflow_json(path: Path) -> dict | list | None:
    """Load workflow JSON from file. Does not classify; use classify_json_for_rag after load."""
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
