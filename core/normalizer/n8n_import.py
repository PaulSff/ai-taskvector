"""
n8n workflow import: map n8n workflow JSON to canonical process graph dict.
"""
import copy
from typing import Any

from core.normalizer.shared import _ensure_list_connections
from core.normalizer.system_comments import N8N_IMPORT_COMMENT_INFO

_N8N_SYSTEM_COMMENT = {
    "id": "comment_system_n8n",
    "info": N8N_IMPORT_COMMENT_INFO,
    "commenter": "System",
    "created_at": "2025-01-01T00:00:00Z",
}
# Keys used for graph structure / identity; do not store in unit.params.
_N8N_STRUCTURE_KEYS = frozenset({"id", "name", "type", "position"})


def _n8n_nodes_list(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract nodes array from n8n workflow JSON (top-level 'nodes')."""
    nodes = raw.get("nodes")
    return nodes if isinstance(nodes, list) else []


def _n8n_connections_to_list(raw: dict[str, Any], node_names: set[str]) -> list[dict[str, Any]]:
    """
    Flatten n8n connections to list of { from, to, from_port, to_port, connection_type? }.
    n8n: { "SourceName": { "main": [[ { "node": "Target", "type": "main", "index": 0 } ], ...] }, "ai_tool": [...] } }.
    The key (main, ai_tool, ai_languageModel, etc.) is the connection type; preserved as connection_type for roundtrip.
    """
    out: list[dict[str, Any]] = []
    conns = raw.get("connections")
    if not isinstance(conns, dict):
        return out
    for source_name, outputs in conns.items():
        if source_name not in node_names or not isinstance(outputs, dict):
            continue
        for output_type, indices_list in outputs.items():
            if not isinstance(indices_list, list):
                continue
            conn_type = str(output_type) if output_type else None
            for from_port_idx, targets in enumerate(indices_list):
                if not isinstance(targets, list):
                    continue
                for t in targets:
                    if isinstance(t, dict) and "node" in t:
                        to_name = t.get("node")
                        to_port = t.get("index", 0)
                        if to_name and to_name in node_names and to_name != source_name:
                            item: dict[str, Any] = {
                                "from": source_name,
                                "to": str(to_name),
                                "from_port": str(from_port_idx),
                                "to_port": str(to_port),
                            }
                            if conn_type:
                                item["connection_type"] = conn_type
                            out.append(item)
    return out


def to_canonical_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Map n8n workflow JSON to canonical process graph dict (environment_type, units, connections, code_blocks).
    n8n format: nodes (array with id, name, type, typeVersion, position, parameters), connections (object
    keyed by node name). We use node name as unit id so connections match. Code from Code node parameters.jsCode → code_blocks.
    """
    nodes = _n8n_nodes_list(raw)
    env_type = str(raw.get("environment_type") or raw.get("process_environment_type") or "").strip()

    unit_ids: set[str] = set()
    units: list[dict[str, Any]] = []
    code_blocks: list[dict[str, Any]] = []

    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("name") or n.get("id")
        if nid is None:
            continue
        nid = str(nid)
        ntype = n.get("type") or "node"
        if isinstance(ntype, str) and "." in ntype:
            ntype = ntype.split(".")[-1]
        ntype = str(ntype)
        unit_ids.add(nid)
        # Preserve all n8n node keys as params (typeVersion, parameters, disabled, notes, etc.)
        params: dict[str, Any] = {}
        for key, val in n.items():
            if key in _N8N_STRUCTURE_KEYS or val is None:
                continue
            try:
                params[key] = copy.deepcopy(val) if isinstance(val, (dict, list)) else val
            except (TypeError, ValueError):
                params[key] = val
        controllable = n.get("controllable")
        if controllable is None:
            controllable = True  # default True on import
        else:
            controllable = bool(controllable)
        # Preserve full n8n type for roundtrip (export uses _n8n_type when present)
        full_type = n.get("type")
        if isinstance(full_type, str) and full_type.strip():
            params["_n8n_type"] = full_type.strip()
        unit_n8n: dict[str, Any] = {"id": nid, "type": ntype, "controllable": controllable, "params": params}
        n8n_name = n.get("name")
        if isinstance(n8n_name, str) and n8n_name.strip():
            unit_n8n["name"] = n8n_name.strip()
        units.append(unit_n8n)

        code_source = (n.get("parameters") or {}).get("jsCode") or (n.get("parameters") or {}).get("code")
        if code_source is not None and isinstance(code_source, str) and code_source.strip():
            code_blocks.append({"id": nid, "language": "javascript", "source": code_source})

    connections = _n8n_connections_to_list(raw, unit_ids)
    # Infer output_ports per unit: one entry per connection type (main, ai_tool, etc.) for roundtrip/UI
    out_types_by_node: dict[str, list[str]] = {}
    for c in connections:
        uid = c.get("from")
        if uid not in unit_ids:
            continue
        ct = c.get("connection_type") or "main"
        if uid not in out_types_by_node:
            out_types_by_node[uid] = []
        if ct not in out_types_by_node[uid]:
            out_types_by_node[uid].append(ct)
    for u in units:
        types_list = out_types_by_node.get(u["id"])
        if types_list:
            u["output_ports"] = [{"name": ct, "type": ct} for ct in sorted(types_list)]
    result: dict[str, Any] = {
        "environment_type": env_type,
        "units": units,
        "connections": _ensure_list_connections(connections),
    }
    if code_blocks:
        result["code_blocks"] = code_blocks
    layout: dict[str, dict[str, float]] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("name") or n.get("id")
        if nid is None or nid not in unit_ids:
            continue
        pos = n.get("position")
        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
            try:
                layout[str(nid)] = {"x": float(pos[0]), "y": float(pos[1])}
            except (TypeError, ValueError):
                pass
        elif isinstance(pos, dict) and "x" in pos and "y" in pos:
            try:
                layout[str(nid)] = {"x": float(pos["x"]), "y": float(pos["y"])}
            except (TypeError, ValueError):
                pass
    if layout:
        result["layout"] = layout
    result["origin"] = {"n8n": {}}
    result["comments"] = [dict(_N8N_SYSTEM_COMMENT)]
    return result
