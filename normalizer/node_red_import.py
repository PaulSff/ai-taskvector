"""
Node-RED flow import: map Node-RED JSON to canonical process graph dict.
Supports multi-tab (flows[] or tab/group nodes with z) and subflows (nested definition preserved).
"""
import copy
from typing import Any

from units.registry import is_controllable_type

# Keys that define graph structure; do not store in unit.params (handled separately).
_NODE_RED_STRUCTURE_KEYS = frozenset({"id", "type", "z", "x", "y", "wires", "name", "label"})


def _node_red_nodes_list(raw: Any) -> list[dict[str, Any]]:
    """Extract flat list of nodes from Node-RED flow (array of nodes, or flows[].nodes, or {nodes})."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        nodes = raw.get("nodes")
        if nodes is not None:
            return nodes
        flows = raw.get("flows")
        if isinstance(flows, list) and flows:
            first = flows[0]
            if isinstance(first, dict) and "nodes" in first:
                return first["nodes"]
            if isinstance(first, list):
                return first
        for key in ("flow", "tab"):
            tab = raw.get(key)
            if isinstance(tab, dict) and "nodes" in tab:
                return tab["nodes"]
            # Library / gist format: "flow" is the nodes array directly
            if isinstance(tab, list) and tab:
                return tab
    return []


def _node_red_flows_list(raw: dict[str, Any]) -> list[dict[str, Any]] | None:
    """If raw has flows[] (list of flow dicts with id/label/nodes), return that list for multi-tab import. Else None."""
    flows = raw.get("flows")
    if not isinstance(flows, list) or not flows:
        return None
    out: list[dict[str, Any]] = []
    for i, f in enumerate(flows):
        if isinstance(f, dict) and ("nodes" in f or isinstance(f.get("nodes"), list)):
            out.append(f)
        elif isinstance(f, list):
            out.append({"id": f"flow_{i}", "label": None, "nodes": f})
    return out if out else None


def _node_red_units_connections_from_nodes(
    nodes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build units, connections, and code_blocks from a list of Node-RED flow nodes (no tab/group nodes). Returns (units, connections, code_blocks)."""
    unit_ids: set[str] = set()
    units: list[dict[str, Any]] = []
    code_blocks: list[dict[str, Any]] = []

    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("id") or n.get("name")
        if nid is None:
            continue
        nid = str(nid)
        raw_type = n.get("type")
        if isinstance(raw_type, str) and raw_type.lower() in ("tab", "group"):
            continue
        ntype = n.get("unitType") or n.get("processType") or raw_type or "node"
        ntype = str(ntype)
        unit_ids.add(nid)
        # Preserve all Node-RED config as params (repeat, crontab, url, method, initialize, finalize, props, etc.),
        # but skip structural keys and code fields (func/code/template/command) since code goes to code_blocks.
        params: dict[str, Any] = {}
        for key, val in n.items():
            if key in _NODE_RED_STRUCTURE_KEYS or key in ("func", "code", "template", "command"):
                continue
            if val is None:
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
        unit: dict[str, Any] = {"id": nid, "type": ntype, "controllable": controllable, "params": params}
        label_or_name = n.get("label") or n.get("name")
        if isinstance(label_or_name, str) and label_or_name.strip():
            unit["name"] = label_or_name.strip()
        # Preserve subflow definition (in, out, configs, nodes) for roundtrip
        if isinstance(raw_type, str) and raw_type.lower() == "subflow":
            subflow_def: dict[str, Any] = {}
            for key in ("in", "out", "configs", "nodes"):
                val = n.get(key)
                if val is not None:
                    subflow_def[key] = copy.deepcopy(val)
            for key in ("name", "info", "env", "meta"):
                val = n.get(key)
                if val is not None:
                    subflow_def[key] = copy.deepcopy(val) if isinstance(val, (dict, list)) else val
            if subflow_def:
                unit["params"]["_node_red_subflow"] = subflow_def
        units.append(unit)
        source = n.get("func") or n.get("code") or n.get("template") or n.get("command")
        if source is not None and isinstance(source, str) and source.strip():
            lang = "shell" if ntype == "exec" else "javascript"
            code_blocks.append({"id": nid, "language": lang, "source": source})

    connections: list[dict[str, Any]] = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        from_id = n.get("id") or n.get("name")
        if from_id is None:
            continue
        from_id = str(from_id)
        wires = n.get("wires") or []
        for out_idx, out_ports in enumerate(wires):
            if not isinstance(out_ports, list):
                continue
            for to_id in out_ports:
                if to_id is None:
                    continue
                to_id = str(to_id)
                if to_id in unit_ids:
                    connections.append({
                        "from": from_id,
                        "to": to_id,
                        "from_port": str(out_idx),
                        "to_port": "0",
                    })
    return (units, connections, code_blocks)


def to_canonical_dict(raw: dict[str, Any] | list[Any]) -> dict[str, Any]:
    """
    Map Node-RED flow JSON to canonical process graph dict (environment_type, units, connections, code_blocks).
    Supports multi-tab: one flow per tab (tabs[].units, tabs[].connections). Top-level units/connections
    mirror the first tab for backward compatibility.
    """
    env_type = "thermodynamic"
    if isinstance(raw, dict):
        env_type = str(raw.get("environment_type", raw.get("process_environment_type", env_type)))

    all_code_blocks: list[dict[str, Any]] = []
    tab_meta_for_origin: list[dict[str, Any]] = []
    tabs_list: list[dict[str, Any]] = []
    layout: dict[str, dict[str, float]] = {}

    flows_list = _node_red_flows_list(raw) if isinstance(raw, dict) else None
    if flows_list is not None:
        for i, flow in enumerate(flows_list):
            tab_id = str(flow.get("id") or f"flow_{i}")
            label = flow.get("label")
            if isinstance(label, str) and not label.strip():
                label = None
            disabled = flow.get("disabled")
            if disabled is not None:
                disabled = bool(disabled)
            tab_meta_for_origin.append({"id": tab_id, "label": label, "disabled": disabled})
            flow_nodes = flow.get("nodes")
            if isinstance(flow_nodes, list):
                for n in flow_nodes:
                    if isinstance(n, dict):
                        nid = n.get("id") or n.get("name")
                        x, y = n.get("x"), n.get("y")
                        if nid is not None and x is not None and y is not None:
                            try:
                                layout[str(nid)] = {"x": float(x), "y": float(y)}
                            except (TypeError, ValueError):
                                pass
                u, c, cb = _node_red_units_connections_from_nodes(flow_nodes)
                all_code_blocks.extend(cb)
                tabs_list.append({
                    "id": tab_id,
                    "label": label,
                    "disabled": disabled,
                    "units": u,
                    "connections": c,
                })
            else:
                tabs_list.append({"id": tab_id, "label": label, "disabled": disabled, "units": [], "connections": []})
        primary_units = tabs_list[0]["units"] if tabs_list else []
        primary_connections = tabs_list[0]["connections"] if tabs_list else []
    else:
        nodes = _node_red_nodes_list(raw)
        tab_nodes_ordered: list[dict[str, Any]] = []
        flow_nodes: list[dict[str, Any]] = []
        for n in nodes:
            if not isinstance(n, dict):
                continue
            raw_type = n.get("type")
            if isinstance(raw_type, str) and raw_type.lower() in ("tab", "group"):
                tab_nodes_ordered.append(n)
            else:
                flow_nodes.append(n)

        if not tab_nodes_ordered:
            primary_units, primary_connections, all_code_blocks = _node_red_units_connections_from_nodes(flow_nodes)
            tabs_list = [{"id": "flow_main", "label": None, "disabled": None, "units": primary_units, "connections": primary_connections}]
            tab_meta_for_origin = [{"id": "flow_main", "label": "Process", "disabled": None}]
        else:
            tab_id_order = [str(t.get("id") or t.get("name") or "") for t in tab_nodes_ordered if t.get("id") or t.get("name")]
            default_z = tab_id_order[0] if tab_id_order else "flow_main"
            by_z: dict[str, list[dict[str, Any]]] = {}
            for n in flow_nodes:
                z = str(n.get("z") or default_z)
                if z not in by_z:
                    by_z[z] = []
                by_z[z].append(n)
            for t in tab_nodes_ordered:
                tid = str(t.get("id") or t.get("name") or "")
                if not tid:
                    continue
                label = t.get("label") or t.get("name")
                if isinstance(label, str) and not label.strip():
                    label = None
                disabled = t.get("disabled")
                if disabled is not None:
                    disabled = bool(disabled)
                tab_meta_for_origin.append({"id": tid, "label": label, "disabled": disabled})
                tab_nodes = by_z.get(tid, [])
                u, c, cb = _node_red_units_connections_from_nodes(tab_nodes)
                all_code_blocks.extend(cb)
                tabs_list.append({"id": tid, "label": label, "disabled": disabled, "units": u, "connections": c})
            for z, tab_nodes in by_z.items():
                if z not in tab_id_order:
                    tab_meta_for_origin.append({"id": z, "label": None, "disabled": None})
                    u, c, cb = _node_red_units_connections_from_nodes(tab_nodes)
                    all_code_blocks.extend(cb)
                    tabs_list.append({"id": z, "label": None, "disabled": None, "units": u, "connections": c})
            primary_units = tabs_list[0]["units"] if tabs_list else []
            primary_connections = tabs_list[0]["connections"] if tabs_list else []
        unit_ids_flat = {str(u["id"]) for u in primary_units}
        for n in flow_nodes:
            if not isinstance(n, dict):
                continue
            nid = n.get("id") or n.get("name")
            if nid is None or nid not in unit_ids_flat:
                continue
            x, y = n.get("x"), n.get("y")
            if x is not None and y is not None:
                try:
                    layout[str(nid)] = {"x": float(x), "y": float(y)}
                except (TypeError, ValueError):
                    pass

    result: dict[str, Any] = {
        "environment_type": env_type,
        "units": primary_units,
        "connections": primary_connections,
    }
    if all_code_blocks:
        result["code_blocks"] = all_code_blocks
    if tab_meta_for_origin:
        result["origin"] = {"node_red": {"tabs": tab_meta_for_origin}}
    if tabs_list:
        result["tabs"] = tabs_list
    if layout:
        result["layout"] = layout
    # Preserve graph-level metadata (readme, summary, gitOwners, etc.) for roundtrip
    if isinstance(raw, dict):
        _skip = {"flow", "flows", "nodes", "environment_type", "process_environment_type"}
        meta = {}
        for k, v in raw.items():
            if k in _skip or v is None:
                continue
            try:
                meta[k] = copy.deepcopy(v) if isinstance(v, (dict, list)) else v
            except (TypeError, ValueError):
                meta[k] = v
        if meta:
            result["metadata"] = meta
    return result
