"""
Ryven project import: map Ryven project JSON to canonical process graph dict.
"""
import copy
from typing import Any

from normalizer.shared import _ensure_list_connections
from units.registry import is_controllable_type

# Keys used for graph structure / identity; do not store in unit.params.
_RYVEN_STRUCTURE_KEYS = frozenset({"id", "name", "type", "title", "identifier", "GID", "__class__"})


def _ryven_flow_and_nodes(raw: dict[str, Any]) -> tuple[dict[str, Any] | None, list[Any]]:
    """Extract flow dict and nodes list from a Ryven project (scripts[].flow or top-level flow)."""
    scripts = raw.get("scripts")
    if isinstance(scripts, list) and scripts and isinstance(scripts[0], dict):
        flow = scripts[0].get("flow")
        if isinstance(flow, dict):
            nodes = flow.get("nodes") or flow.get("node_list") or flow.get("nodes_list") or []
            return flow, nodes if isinstance(nodes, list) else []
    flow = raw.get("flow")
    if isinstance(flow, dict):
        nodes = flow.get("nodes") or flow.get("node_list") or []
        return flow, nodes if isinstance(nodes, list) else []
    nodes = raw.get("nodes") or raw.get("node_list") or []
    return raw, nodes if isinstance(nodes, list) else []


def _ryven_connections_list(flow: dict[str, Any] | None, node_ids: set[str]) -> list[dict[str, Any]]:
    """Extract connections from Ryven flow. Parse nodeId:port for from_port/to_port when present."""
    if flow is None:
        return []
    conns = flow.get("connections") or flow.get("links") or flow.get("edges") or flow.get("wires") or []
    if not isinstance(conns, list):
        return []
    out: list[dict[str, Any]] = []
    for c in conns:
        if not isinstance(c, dict):
            continue
        from_raw = c.get("from") or c.get("from_node") or c.get("from_id") or c.get("source")
        to_raw = c.get("to") or c.get("to_node") or c.get("to_id") or c.get("target")
        if from_raw is None or to_raw is None:
            continue
        from_id, from_port = (str(from_raw).split(":", 1) + ["0"])[:2]
        to_id, to_port = (str(to_raw).split(":", 1) + ["0"])[:2]
        from_port = from_port or "0"
        to_port = to_port or "0"
        if from_id in node_ids and to_id in node_ids:
            out.append({"from": from_id, "to": to_id, "from_port": from_port, "to_port": to_port})
    return out


def to_canonical_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Map Ryven project JSON to canonical process graph dict (environment_type, units, connections, code_blocks).
    Ryven layout: scripts[].flow with nodes and connections/links; or top-level flow/nodes.
    """
    flow, nodes = _ryven_flow_and_nodes(raw)
    env_type = str(raw.get("environment_type", raw.get("process_environment_type", "thermodynamic")))
    unit_ids: set[str] = set()
    units: list[dict[str, Any]] = []
    code_blocks: list[dict[str, Any]] = []

    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("id") or n.get("name") or n.get("identifier") or n.get("GID")
        if nid is None:
            continue
        nid = str(nid)
        ntype = n.get("type") or n.get("title") or n.get("node_type") or n.get("identifier") or n.get("__class__") or "Node"
        if isinstance(ntype, dict):
            ntype = ntype.get("name", "Node")
        ntype = str(ntype).split(".")[-1]
        unit_ids.add(nid)
        # Preserve all Ryven node keys as params (data, params, parameters, etc.)
        params: dict[str, Any] = {}
        for key, val in n.items():
            if key in _RYVEN_STRUCTURE_KEYS or val is None:
                continue
            try:
                params[key] = copy.deepcopy(val) if isinstance(val, (dict, list)) else val
            except (TypeError, ValueError):
                params[key] = val
        controllable = n.get("controllable")
        if controllable is None:
            controllable = is_controllable_type(ntype)
        else:
            controllable = bool(controllable)
        unit_rv: dict[str, Any] = {"id": nid, "type": ntype, "controllable": controllable, "params": params}
        rv_name = n.get("title") or n.get("name")
        if isinstance(rv_name, str) and rv_name.strip():
            unit_rv["name"] = rv_name.strip()
        units.append(unit_rv)

        # Extract code for code_blocks.
        # Ryven often stores code under node["data"]["source"] or similar, so look there as well.
        data = n.get("data") if isinstance(n.get("data"), dict) else None
        source = n.get("source") or n.get("code") or n.get("script")
        if source is None and isinstance(data, dict):
            source = data.get("source") or data.get("code") or data.get("script")
        if source is None:
            source = params.get("source") or params.get("code")
        if source is not None and isinstance(source, str) and source.strip():
            lang = n.get("language")
            if lang is None and isinstance(data, dict):
                lang = data.get("language")
            if lang is None:
                lang = params.get("language") or "python"
            code_blocks.append({
                "id": nid,
                "language": str(lang),
                "source": source,
            })

    connections = _ryven_connections_list(flow, unit_ids)
    result: dict[str, Any] = {
        "environment_type": env_type,
        "units": units,
        "connections": _ensure_list_connections(connections) if connections else [],
    }
    if code_blocks:
        result["code_blocks"] = code_blocks
    result["origin"] = {"ryven": {}}
    return result
