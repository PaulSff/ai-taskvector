"""
Export canonical ProcessGraph to external runtime formats (Node-RED, PyFlow, n8n).

Enables roundtrip: import → edit → export to run in Node-RED, PyFlow, or n8n.
Units and connections map 1:1; code_blocks become func/code on nodes.
Canonical units (step_driver, join, switch, split, step_rewards) without code_blocks get template
code injected at export so the full setup is runnable (see deploy.canonical_inject).
"""
from __future__ import annotations

from typing import Any, Literal

from schemas.process_graph import ProcessGraph

ExportFormat = Literal["node_red", "pyflow", "n8n", "comfyui"]

# Map canonical unit types to Node-RED platform node types (when no code_block)
NODE_RED_TYPE_MAP: dict[str, str] = {
    "HttpIn": "http in",
    "HttpResponse": "http response",
}


def _enriched_code_by_id(graph: ProcessGraph, export_format: str) -> dict[str, str]:
    """Code map from graph code_blocks plus injected code for canonical units (no existing block)."""
    code_map = {b.id: b.source for b in graph.code_blocks}
    try:
        from deploy.canonical_inject import enrich_code_map_for_export
        return enrich_code_map_for_export(graph, code_map, export_format)
    except Exception:
        return code_map


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


def _node_red_output_port_index(unit: Any, from_port: str) -> int:
    """
    Resolve from_port to numeric output port index for Node-RED wires.
    from_port can be an index string ('0', '1') or a port name (e.g. 'else', 'Rule: gte 0').
    Aligns with import: switch/trigger/function use names in output_ports.
    """
    if not from_port:
        return 0
    try:
        return int(from_port)
    except (ValueError, TypeError):
        pass
    if not unit.output_ports:
        return 0
    for i, p in enumerate(unit.output_ports):
        if p.name == from_port:
            return i
    return 0


def _node_red_flow_node(
    u: Any,
    x: float,
    y: float,
    z: str,
    wires_array: list[list[str]],
    code_map: dict[str, str],
) -> dict[str, Any]:
    """Build one Node-RED flow node from a Unit. Handles subflow (preserves in, out, configs, nodes)."""
    params = dict(u.params) if u.params else {}
    subflow_def = params.pop("_node_red_subflow", None)
    if u.type == "subflow" and isinstance(subflow_def, dict):
        node: dict[str, Any] = {
            "id": u.id,
            "type": "subflow",
            "name": subflow_def.get("name") or u.name or "Subflow",
            "x": x,
            "y": y,
            "z": z,
            "wires": wires_array,
            "params": params,
        }
        for key in ("in", "out", "configs", "nodes"):
            if key in subflow_def:
                node[key] = subflow_def[key]
        for key in ("info", "env", "meta"):
            if key in subflow_def:
                node[key] = subflow_def[key]
        # Flatten remaining params to top-level so re-import preserves category, color, etc.
        for k, v in params.items():
            if not k.startswith("_") and k not in node:
                node[k] = v
        return node
    has_code = u.id in code_map
    node_type = "function" if has_code else NODE_RED_TYPE_MAP.get(u.type, u.type)
    node: dict[str, Any] = {
        "id": u.id,
        "type": node_type,
        "x": x,
        "y": y,
        "z": z,
        "wires": wires_array,
    }
    if u.name:
        node["name"] = u.name
    # Flatten params to top-level so Node-RED gets repeat, url, method, initialize, finalize, etc.
    for k, v in params.items():
        if not k.startswith("_"):
            node[k] = v
    if has_code:
        node["func"] = code_map[u.id]
        if u.type not in ("function", "Function"):
            node["unitType"] = u.type
    # Node-RED multi-output nodes (e.g. function) need explicit outputs property
    if len(wires_array) > 1:
        node["outputs"] = len(wires_array)
    return node


def from_process_graph_to_node_red(graph: ProcessGraph) -> list[dict[str, Any]] | dict[str, Any]:
    """
    Convert ProcessGraph to Node-RED flow format.

    Returns array of nodes: [tab1, tab2, ... flow nodes for tab1, ... flow nodes for tab2, ...].
    When graph.tabs is set, one tab node per tab and each tab's units with z=tab.id; else single "Process" tab.
    Code_blocks and layout are global (by unit id).

    Aligned with node_red_import: wires[i] = port i; from_port resolved by index or output_ports name
    (switch/trigger/function); num_ports from connections or unit.output_ports; outputs set for multi-port nodes.
    """
    code_map = _enriched_code_by_id(graph, "node_red")

    if graph.tabs:
        # Multi-tab: one tab node per tab, then each tab's units with z = tab.id
        nodes: list[dict[str, Any]] = []
        for tab in graph.tabs:
            fallback_pos = _layered_layout(tab.units, tab.connections)
            tab_node: dict[str, Any] = {"id": tab.id, "type": "tab", "label": tab.label or "Flow"}
            nodes.append(tab_node)
            unit_ids = {u.id for u in tab.units}
            id_to_unit = {u.id: u for u in tab.units}
            wires_by_port: dict[str, dict[int, list[str]]] = {uid: {} for uid in unit_ids}
            for c in tab.connections:
                if c.from_id in unit_ids and c.to_id in unit_ids:
                    unit = id_to_unit.get(c.from_id)
                    port_idx = _node_red_output_port_index(unit, c.from_port or "0")
                    if port_idx not in wires_by_port[c.from_id]:
                        wires_by_port[c.from_id][port_idx] = []
                    wires_by_port[c.from_id][port_idx].append(c.to_id)
            for u in tab.units:
                x, y = _get_position(u.id, graph, fallback_pos)
                port_map = wires_by_port.get(u.id, {})
                max_port = max(port_map.keys(), default=-1)
                num_ports = max_port + 1 if max_port >= 0 else 0
                if u.output_ports:
                    num_ports = max(num_ports, len(u.output_ports))
                if num_ports == 0:
                    num_ports = 1
                wires_array = [port_map.get(i, []) for i in range(num_ports)]
                nodes.append(_node_red_flow_node(u, x, y, tab.id, wires_array, code_map))
        if getattr(graph, "metadata", None) and isinstance(graph.metadata, dict) and graph.metadata:
            out_tabs: dict[str, Any] = {"flow": nodes}
            for k, v in graph.metadata.items():
                if v is not None and not k.startswith("_"):
                    out_tabs[k] = v
            return out_tabs
        return nodes

    # Single-tab (current behavior)
    unit_ids = {u.id for u in graph.units}
    id_to_unit = {u.id: u for u in graph.units}
    fallback_pos = _default_positions(graph)
    wires_by_port: dict[str, dict[int, list[str]]] = {uid: {} for uid in unit_ids}
    for c in graph.connections:
        if c.from_id in unit_ids and c.to_id in unit_ids:
            unit = id_to_unit.get(c.from_id)
            port_idx = _node_red_output_port_index(unit, c.from_port or "0")
            if port_idx not in wires_by_port[c.from_id]:
                wires_by_port[c.from_id][port_idx] = []
            wires_by_port[c.from_id][port_idx].append(c.to_id)

    flow_id = "flow_main"
    tab_node = {"id": flow_id, "type": "tab", "label": "Process"}
    nodes = [tab_node]
    for u in graph.units:
        x, y = _get_position(u.id, graph, fallback_pos)
        port_map = wires_by_port.get(u.id, {})
        max_port = max(port_map.keys(), default=-1)
        num_ports = max_port + 1 if max_port >= 0 else 0
        if u.output_ports:
            num_ports = max(num_ports, len(u.output_ports))
        if num_ports == 0:
            num_ports = 1
        wires_array = [port_map.get(i, []) for i in range(num_ports)]
        nodes.append(_node_red_flow_node(u, x, y, flow_id, wires_array, code_map))
    if getattr(graph, "metadata", None) and isinstance(graph.metadata, dict) and graph.metadata:
        out: dict[str, Any] = {"flow": nodes}
        for k, v in graph.metadata.items():
            if v is not None and not k.startswith("_"):
                out[k] = v
        return out
    return nodes


def from_process_graph_to_pyflow(graph: ProcessGraph) -> dict[str, Any]:
    """
    Convert ProcessGraph to PyFlow graph format (nodes + connections).

    Nodes have id, name, type, params, code (if code_block). Connections use from/to.
    """
    unit_ids = {u.id for u in graph.units}
    fallback_pos = _default_positions(graph)
    code_map = _enriched_code_by_id(graph, "pyflow")

    nodes: list[dict[str, Any]] = []
    for u in graph.units:
        x, y = _get_position(u.id, graph, fallback_pos)
        params = dict(u.params) if u.params else {}
        node: dict[str, Any] = {
            "id": u.id,
            "name": u.id,
            "type": u.type,
            "x": params.pop("x", x),
            "y": params.pop("y", y),
        }
        for k, v in params.items():
            if not k.startswith("_"):
                node[k] = v
        if u.id in code_map:
            node["code"] = code_map[u.id]
        nodes.append(node)

    connections = [
        {
            "from": c.from_id,
            "to": c.to_id,
            "from_port": c.from_port,
            "to_port": c.to_port,
        }
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
    code_map = _enriched_code_by_id(graph, "n8n")

    nodes: list[dict[str, Any]] = []
    for u in graph.units:
        x, y = _get_position(u.id, graph, fallback_pos)
        params = dict(u.params) if u.params else {}
        # Preserve original n8n type for roundtrip when present
        ntype = params.pop("_n8n_type", None) or u.type
        if u.id in code_map and ntype == u.type:
            ntype = "n8n-nodes-base.code"
        elif isinstance(ntype, str) and "." not in ntype and not ntype.startswith("@"):
            ntype = f"n8n-nodes-base.{ntype}"
        node: dict[str, Any] = {
            "id": u.id,
            "name": u.id,
            "type": ntype,
            "typeVersion": params.pop("typeVersion", 1),
            "position": params.pop("position", None) or [x, y],
            "parameters": params.pop("parameters", dict(params)),
        }
        if u.id in code_map:
            node["parameters"] = {**node.get("parameters", {}), "jsCode": code_map[u.id]}
        for k, v in params.items():
            if not k.startswith("_"):
                node[k] = v
        nodes.append(node)

    # Build connections: n8n { nodeName: { outputType: [[{node, type, index}], ...] } }; use connection_type (main, ai_tool, etc.)
    out_by_type_port: dict[str, dict[str, dict[int, list[dict[str, Any]]]]] = {}  # from_id -> type -> port_idx -> targets
    for c in graph.connections:
        if c.from_id not in unit_ids or c.to_id not in unit_ids:
            continue
        try:
            from_port_idx = int(c.from_port) if c.from_port else 0
        except (ValueError, TypeError):
            from_port_idx = 0
        try:
            to_port_idx = int(c.to_port) if c.to_port else 0
        except (ValueError, TypeError):
            to_port_idx = 0
        conn_type = (c.connection_type or "main").strip() or "main"
        if c.from_id not in out_by_type_port:
            out_by_type_port[c.from_id] = {}
        if conn_type not in out_by_type_port[c.from_id]:
            out_by_type_port[c.from_id][conn_type] = {}
        if from_port_idx not in out_by_type_port[c.from_id][conn_type]:
            out_by_type_port[c.from_id][conn_type][from_port_idx] = []
        out_by_type_port[c.from_id][conn_type][from_port_idx].append({
            "node": c.to_id,
            "type": conn_type,
            "index": to_port_idx,
        })

    connections: dict[str, Any] = {}
    for uid in unit_ids:
        type_port_map = out_by_type_port.get(uid, {})
        connections[uid] = {}
        for conn_type, port_map in type_port_map.items():
            max_port = max(port_map.keys(), default=-1)
            connections[uid][conn_type] = [port_map.get(i, []) for i in range(max_port + 1)] if max_port >= 0 else [[]]
        if not connections[uid]:
            connections[uid] = {"main": [[]]}

    return {
        "nodes": nodes,
        "connections": connections,
        "environment_type": graph.environment_type.value,
    }


def from_process_graph_to_comfyui(graph: ProcessGraph) -> dict[str, Any]:
    """
    Convert ProcessGraph to ComfyUI workflow format (nodes + links).

    ComfyUI v1.0: nodes (id, type, pos, size, flags, order, mode, properties, inputs, outputs, widgets_values),
    links (id, origin_id, origin_slot, target_id, target_slot, type).
    """
    unit_ids = {u.id for u in graph.units}
    fallback_pos = _default_positions(graph)
    code_map = _code_by_id(graph)

    # Assign link ids for each connection
    link_id = 1
    link_map: dict[tuple[str, int, str, int], int] = {}  # (from_id, fp, to_id, tp) -> link_id
    for c in graph.connections:
        if c.from_id not in unit_ids or c.to_id not in unit_ids:
            continue
        try:
            fp = int(c.from_port) if c.from_port else 0
        except (ValueError, TypeError):
            fp = 0
        try:
            tp = int(c.to_port) if c.to_port else 0
        except (ValueError, TypeError):
            tp = 0
        key = (c.from_id, fp, c.to_id, tp)
        if key not in link_map:
            link_map[key] = link_id
            link_id += 1

    nodes_out: list[dict[str, Any]] = []
    for idx, u in enumerate(graph.units):
        x, y = _get_position(u.id, graph, fallback_pos)
        ntype = u.type
        params = dict(u.params) if u.params else {}
        widgets = params.pop("widgets_values", None)
        size = params.pop("_comfy_size", None) or params.pop("size", None)
        flags = params.pop("_comfy_flags", None) or params.pop("flags", None)
        order = params.pop("_comfy_order", None) or params.pop("order", None)
        mode = params.pop("_comfy_mode", None) or params.pop("mode", None)
        properties = params.pop("_comfy_properties", None) or params.pop("properties", None)
        if widgets is None and params:
            widgets = list(params.values()) if params else []

        inputs_by_slot: dict[int, int] = {}
        for c in graph.connections:
            if c.to_id != u.id:
                continue
            try:
                tp = int(c.to_port) if c.to_port else 0
            except (ValueError, TypeError):
                tp = 0
            key = (c.from_id, int(c.from_port or 0), u.id, tp)
            if key in link_map and tp not in inputs_by_slot:
                inputs_by_slot[tp] = link_map[key]
        max_in = max(inputs_by_slot.keys(), default=-1)
        if u.input_ports:
            max_in = max(max_in, len(u.input_ports) - 1)
        inputs_list = []
        for slot in range(max_in + 1):
            port_spec = u.input_ports[slot] if u.input_ports and slot < len(u.input_ports) else None
            link_id = inputs_by_slot.get(slot)
            inp: dict[str, Any] = {
                "name": port_spec.name if port_spec else f"input_{slot}",
                "type": (port_spec.type if port_spec else None) or "FLOAT",
            }
            if link_id is not None:
                inp["link"] = link_id
            inputs_list.append(inp)

        out_links_by_slot: dict[int, list[int]] = {}
        for c in graph.connections:
            if c.from_id != u.id:
                continue
            try:
                fp = int(c.from_port) if c.from_port else 0
            except (ValueError, TypeError):
                fp = 0
            key = (u.id, fp, c.to_id, int(c.to_port or 0))
            if key in link_map:
                if fp not in out_links_by_slot:
                    out_links_by_slot[fp] = []
                out_links_by_slot[fp].append(link_map[key])
        max_out = max(out_links_by_slot.keys(), default=-1)
        if u.output_ports:
            max_out = max(max_out, len(u.output_ports) - 1)
        outputs_list = []
        for slot in range(max_out + 1):
            port_spec = u.output_ports[slot] if u.output_ports and slot < len(u.output_ports) else None
            links = out_links_by_slot.get(slot) or []
            outputs_list.append({
                "name": port_spec.name if port_spec else f"output_{slot}",
                "type": (port_spec.type if port_spec else None) or "FLOAT",
                "links": links,
            })

        node: dict[str, Any] = {
            "id": u.id,
            "type": ntype,
            "pos": [x, y],
            "size": size if isinstance(size, (list, tuple)) and len(size) >= 2 else [315, 58],
            "flags": flags if isinstance(flags, dict) else {},
            "order": int(order) if order is not None else idx,
            "mode": int(mode) if mode is not None else 0,
            "properties": properties if isinstance(properties, dict) else {},
            "inputs": inputs_list,
            "outputs": outputs_list,
        }
        if widgets is not None:
            node["widgets_values"] = widgets
        if u.id in code_map:
            node["params"] = {**(node.get("params") or {}), "source": code_map[u.id]}
        elif params:
            node["params"] = params
        nodes_out.append(node)

    links_out: list[dict[str, Any]] = []
    for c in graph.connections:
        if c.from_id not in unit_ids or c.to_id not in unit_ids:
            continue
        try:
            fp = int(c.from_port) if c.from_port else 0
        except (ValueError, TypeError):
            fp = 0
        try:
            tp = int(c.to_port) if c.to_port else 0
        except (ValueError, TypeError):
            tp = 0
        key = (c.from_id, fp, c.to_id, tp)
        if key not in link_map:
            continue
        lid = link_map[key]
        link_type: Any = "FLOAT"
        if c.connection_type is not None and c.connection_type.strip():
            link_type = c.connection_type
        links_out.append({
            "id": lid,
            "origin_id": c.from_id,
            "origin_slot": fp,
            "target_id": c.to_id,
            "target_slot": tp,
            "type": link_type,
        })

    last_node_id = 0
    for u in graph.units:
        try:
            last_node_id = max(last_node_id, int(u.id))
        except (ValueError, TypeError):
            pass
    return {
        "version": 1,
        "state": {
            "lastGroupid": 0,
            "lastNodeId": last_node_id,
            "lastLinkId": link_id - 1,
            "lastRerouteId": 0,
        },
        "nodes": nodes_out,
        "links": links_out,
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
    if format == "comfyui":
        return from_process_graph_to_comfyui(graph)
    raise ValueError(f"Unknown export format: {format}")
