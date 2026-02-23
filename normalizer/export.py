"""
Export canonical ProcessGraph to external runtime formats (Node-RED, PyFlow, n8n).

Enables roundtrip: import → edit → export to run in Node-RED, PyFlow, or n8n.
Units and connections map 1:1; code_blocks become func/code on nodes.
"""
from __future__ import annotations

from typing import Any, Literal

from schemas.process_graph import ProcessGraph

ExportFormat = Literal["node_red", "pyflow", "n8n"]


def _layered_layout(unit_list: list, conn_list: list) -> dict[str, tuple[float, float]]:
    """Assign positions with a left-to-right layered layout. Returns unit_id -> (x, y)."""
    unit_ids = [u.id for u in unit_list]
    id_to_idx = {uid: i for i, uid in enumerate(unit_ids)}
    preds: dict[str, list[str]] = {uid: [] for uid in unit_ids}
    for c in conn_list:
        if c.from_id in id_to_idx and c.to_id in id_to_idx and c.from_id != c.to_id:
            preds[c.to_id].append(c.from_id)

    layers: list[list[str]] = []
    assigned: set[str] = set()

    def has_all_preds_assigned(uid: str) -> bool:
        return all(p in assigned for p in preds[uid])

    while len(assigned) < len(unit_ids):
        layer = [uid for uid in unit_ids if uid not in assigned and has_all_preds_assigned(uid)]
        if not layer:
            layer = [uid for uid in unit_ids if uid not in assigned]
        for uid in layer:
            assigned.add(uid)
        layers.append(layer)

    for layer_idx in range(1, len(layers)):
        prev_layer = layers[layer_idx - 1]
        prev_order = {uid: i for i, uid in enumerate(prev_layer)}

        def key(uid: str) -> float:
            p = preds[uid]
            if not p:
                return 0.0
            return sum(prev_order.get(x, 0) for x in p) / len(p)

        layers[layer_idx] = sorted(layers[layer_idx], key=key)

    dx, dy = 260.0, 100.0
    x0, y0 = 80.0, 60.0
    positions: dict[str, tuple[float, float]] = {}
    for li, layer in enumerate(layers):
        base_y = y0 - (len(layer) - 1) * dy / 2 if layer else 0.0
        for ni, uid in enumerate(layer):
            positions[uid] = (x0 + li * dx, base_y + ni * dy)
    return positions


def _default_positions(graph: ProcessGraph) -> dict[str, tuple[float, float]]:
    """Layered layout when graph.layout is missing. Returns unit_id -> (x, y)."""
    return _layered_layout(graph.units, graph.connections)


def _get_position(
    unit_id: str,
    graph: ProcessGraph,
    fallback: dict[str, tuple[float, float]],
) -> tuple[float, float]:
    if graph.layout and unit_id in graph.layout:
        pos = graph.layout[unit_id]
        return (pos.x, pos.y)
    return fallback.get(unit_id, (100.0, 100.0))


def _code_by_id(graph: ProcessGraph) -> dict[str, str]:
    return {b.id: b.source for b in graph.code_blocks}


def from_process_graph_to_node_red(graph: ProcessGraph) -> list[dict[str, Any]] | dict[str, Any]:
    """
    Convert ProcessGraph to Node-RED flow format.

    Returns array of nodes: [tab, ...flow nodes]. Each unit → node with id, type, x, y, z, wires, params.
    Code_blocks → func on node. Connections become wires: node A wires[0] = [B, C] for A→B and A→C.
    """
    unit_ids = {u.id for u in graph.units}
    fallback_pos = _default_positions(graph)
    code_map = _code_by_id(graph)

    # Build wires: from_id -> list of to_ids (output port 0)
    wires_out: dict[str, list[str]] = {uid: [] for uid in unit_ids}
    for c in graph.connections:
        if c.from_id in unit_ids and c.to_id in unit_ids:
            wires_out[c.from_id].append(c.to_id)

    flow_id = "flow_main"
    tab_node: dict[str, Any] = {"id": flow_id, "type": "tab", "label": "Process"}
    nodes: list[dict[str, Any]] = [tab_node]
    for u in graph.units:
        x, y = _get_position(u.id, graph, fallback_pos)
        has_code = u.id in code_map
        node: dict[str, Any] = {
            "id": u.id,
            "type": "function" if has_code else u.type,
            "x": x,
            "y": y,
            "z": flow_id,
            "wires": [wires_out.get(u.id, [])],
            "params": dict(u.params) if u.params else {},
        }
        if has_code:
            node["func"] = code_map[u.id]
            if u.type not in ("function", "Function"):
                node["params"] = {**node.get("params", {}), "unitType": u.type}
        nodes.append(node)

    # Node-RED accepts array of nodes (tab first, then flow nodes)
    return nodes


def from_process_graph_to_pyflow(graph: ProcessGraph) -> dict[str, Any]:
    """
    Convert ProcessGraph to PyFlow graph format (nodes + connections).

    Nodes have id, name, type, params, code (if code_block). Connections use from/to.
    """
    unit_ids = {u.id for u in graph.units}
    fallback_pos = _default_positions(graph)
    code_map = _code_by_id(graph)

    nodes: list[dict[str, Any]] = []
    for u in graph.units:
        x, y = _get_position(u.id, graph, fallback_pos)
        node: dict[str, Any] = {
            "id": u.id,
            "name": u.id,
            "type": u.type,
            "params": dict(u.params) if u.params else {},
            "x": x,
            "y": y,
        }
        if u.id in code_map:
            node["code"] = code_map[u.id]
        nodes.append(node)

    connections = [
        {"from": c.from_id, "to": c.to_id}
        for c in graph.connections
        if c.from_id in unit_ids and c.to_id in unit_ids
    ]

    return {
        "nodes": nodes,
        "connections": connections,
        "environment_type": graph.environment_type.value,
    }


def from_process_graph_to_n8n(graph: ProcessGraph) -> dict[str, Any]:
    """
    Convert ProcessGraph to n8n workflow format (nodes + connections keyed by name).

    n8n connections: { "NodeName": { "main": [[ {node, type, index} ]] } }.
    Code nodes use n8n-nodes-base.code with parameters.jsCode.
    """
    unit_ids = {u.id for u in graph.units}
    fallback_pos = _default_positions(graph)
    code_map = _code_by_id(graph)

    nodes: list[dict[str, Any]] = []
    for u in graph.units:
        x, y = _get_position(u.id, graph, fallback_pos)
        ntype = u.type
        # Map generic types to n8n node types where applicable
        if u.id in code_map:
            ntype = "n8n-nodes-base.code"
        node: dict[str, Any] = {
            "id": u.id,
            "name": u.id,
            "type": ntype,
            "typeVersion": 1,
            "position": [x, y],
            "parameters": dict(u.params) if u.params else {},
        }
        if u.id in code_map:
            node["parameters"] = {**node.get("parameters", {}), "jsCode": code_map[u.id]}
        nodes.append(node)

    # Build connections: from_name -> list of targets for main output
    out_targets: dict[str, list[dict[str, Any]]] = {uid: [] for uid in unit_ids}
    for c in graph.connections:
        if c.from_id in unit_ids and c.to_id in unit_ids:
            out_targets[c.from_id].append({"node": c.to_id, "type": "main", "index": 0})

    connections: dict[str, Any] = {}
    for uid in unit_ids:
        targets = out_targets.get(uid, [])
        connections[uid] = {"main": [targets]}

    return {
        "nodes": nodes,
        "connections": connections,
        "environment_type": graph.environment_type.value,
    }


def from_process_graph(
    graph: ProcessGraph,
    format: ExportFormat,
) -> dict[str, Any] | list[dict[str, Any]]:
    """
    Export ProcessGraph to external runtime format.

    Args:
        graph: Canonical process graph (with optional oracles, RL agents, code_blocks).
        format: "node_red" | "pyflow" | "n8n".

    Returns:
        Raw flow/workflow dict suitable for import into Node-RED, PyFlow, or n8n.
    """
    if format == "node_red":
        return from_process_graph_to_node_red(graph)
    if format == "pyflow":
        return from_process_graph_to_pyflow(graph)
    if format == "n8n":
        return from_process_graph_to_n8n(graph)
    raise ValueError(f"Unknown export format: {format}")
