"""
Node-RED flow import: map Node-RED JSON to canonical process graph dict.
Supports multi-tab (flows[] or tab/group nodes with z) and subflows (nested definition preserved).

Port resolution (Node-RED semantics):
- wires[i] = list of destination node IDs for output port i (index = port).
- Single port: wires = [["n1","n2"]]; multiple: wires = [["n1"],["n2"]].
- Input: one logical input per node carrying msg; input_ports name "msg", type JavaScript(object).
- Function nodes: outputs/return array index maps to port index (return [msg,null] → port 0 gets msg, port 1 skipped).
- Port type is always JavaScript(object) for msg; output port names use msg property paths (e.g. msg.parts, msg.payload[0].feedback).
"""
import copy
import re
from typing import Any

from units.registry import is_controllable_type

# Keys that define graph structure; do not store in unit.params (handled separately).
_NODE_RED_STRUCTURE_KEYS = frozenset({"id", "type", "z", "x", "y", "wires", "name", "label"})

# Port type for Node-RED message object (msg is a JavaScript object).
_NODE_RED_MSG_TYPE = "JavaScript(object)"


def _node_red_output_port_count(node: dict[str, Any]) -> int:
    """Return number of output ports from wires. wires[i] = destinations for port i."""
    wires = node.get("wires")
    if not isinstance(wires, list):
        return 0
    return len(wires)


def _node_red_switch_output_ports(node: dict[str, Any], num_ports: int) -> list[dict[str, str]] | None:
    """
    Return output port specs for a switch node from rules (doc + 10-switch_spec.js).
    rules[i] maps to output port i; rule "t" (eq, gte, lte, else, ...) and "v"/"v2" define the branch.
    """
    rules = node.get("rules")
    if not isinstance(rules, list) or len(rules) != num_ports:
        return None
    out: list[dict[str, str]] = []
    for r in rules:
        if not isinstance(r, dict):
            out.append({"name": str(len(out)), "type": _NODE_RED_MSG_TYPE})
            continue
        t = r.get("t") or "eq"
        if t == "else":
            out.append({"name": "else", "type": _NODE_RED_MSG_TYPE})
        else:
            v = r.get("v", "")
            v2 = r.get("v2")
            if v2 is not None and str(v2) != "":
                label = f"Rule: {t} {v}..{v2}"
            else:
                label = f"Rule: {t} {v}" if v != "" else f"Rule: {t}"
            out.append({"name": label.strip(), "type": _NODE_RED_MSG_TYPE})
    return out if out else None


def _node_red_trigger_output_ports(node: dict[str, Any], num_ports: int) -> list[dict[str, str]] | None:
    """
    Return output port specs for a trigger node (doc + 89-trigger_spec.js).
    Output 0 = immediate (op1), Output 1 = delayed (op2) when outputs: 2.
    """
    if num_ports == 1:
        op1 = node.get("op1")
        op1type = node.get("op1type") or "str"
        name = str(op1) if op1 is not None else "immediate"
        return [{"name": name, "type": str(op1type).lower()}]
    if num_ports == 2:
        op1 = node.get("op1")
        op2 = node.get("op2")
        op1type = node.get("op1type") or "str"
        op2type = node.get("op2type") or "str"
        return [
            {"name": str(op1) if op1 is not None else "immediate", "type": str(op1type).lower()},
            {"name": str(op2) if op2 is not None else "delayed", "type": str(op2type).lower()},
        ]
    return None


def _node_red_inject_output_port(node: dict[str, Any]) -> dict[str, str] | None:
    """
    Return output port spec for an inject node from its parameters.
    Inject always outputs one message; format comes from payloadType / props.
    e.g. payloadType "json" -> name "payload", type "json".
    """
    # Primary property is payload; type from payloadType (json, str, num, bool, date, buffer, etc.)
    payload_type = node.get("payloadType")
    if isinstance(payload_type, str) and payload_type.strip():
        type_str = payload_type.strip().lower()
    else:
        # Fallback: first prop's vt (value type) from props array
        props = node.get("props")
        if isinstance(props, list) and props and isinstance(props[0], dict):
            vt = props[0].get("vt")
            if isinstance(vt, str) and vt.strip():
                type_str = vt.strip().lower()
            else:
                type_str = "json"
        else:
            type_str = "json"
    return {"name": "payload", "type": type_str}


def _node_red_parse_msg_property_paths(func_source: str) -> list[str]:
    """
    Extract msg property paths from function code in order of first occurrence.
    e.g. msg.payload[0].feedback -> "msg.payload[0].feedback". msg.payload is the message body.
    Returns unique full paths (msg.<path>) suitable for port names.
    """
    if not func_source or not isinstance(func_source, str):
        return []
    # Match msg.<ident>, msg.payload[0], msg.payload[0].feedback, etc.
    pattern = r"msg\.(\w+(?:\[\d+\])?(?:\.\w+)*)"
    seen: set[str] = set()
    result: list[str] = []
    for m in re.finditer(pattern, func_source):
        path = m.group(1)
        full = "msg." + path
        if full not in seen:
            seen.add(full)
            result.append(full)
    return result


def _node_red_parse_function_return_ports(func_source: str, num_ports: int) -> list[str] | None:
    """
    Parse function node code for return [...]; pattern. Array index = output port index.
    Returns list of port semantic hints ("msg" or "skip") for which ports carry a message.
    """
    if not func_source or num_ports <= 0:
        return None
    # Match return [ ... ]; (single-line or multi-line; capture content between brackets)
    m = re.search(r"return\s*\[(.*?)\]\s*;", func_source, re.DOTALL)
    if not m:
        # Single return: return msg; → one output
        if re.search(r"return\s+\w+\s*;", func_source) and num_ports == 1:
            return ["msg"]
        return None
    inner = m.group(1)
    # Split by comma, but be naive (no nested brackets); good enough for return [msg,null]; etc.
    parts = re.split(r",", inner)
    names: list[str] = []
    for i, part in enumerate(parts):
        if i >= num_ports:
            break
        part = part.strip()
        if re.match(r"null\s*$", part) or part == "":
            names.append("skip")
        else:
            names.append("msg")
    while len(names) < num_ports:
        names.append("msg")
    return names[:num_ports]


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
        # Resolve output_ports from wires: wires[i] = destinations for port i. Type = JavaScript(object); names = msg property paths.
        num_out = _node_red_output_port_count(n)
        if num_out == 1:
            if isinstance(raw_type, str) and raw_type.lower() == "inject":
                unit["output_ports"] = [_node_red_inject_output_port(n)]
            elif isinstance(raw_type, str) and raw_type.lower() == "split":
                # Split: single output with msg.parts metadata (doc + 17-split_spec.js); type remains JavaScript(object)
                unit["output_ports"] = [{"name": "msg.parts", "type": _NODE_RED_MSG_TYPE}]
            elif raw_type == "function":
                func_src = n.get("func") or ""
                if isinstance(func_src, str):
                    paths = _node_red_parse_msg_property_paths(func_src)
                    if paths:
                        # Name from first msg property path (e.g. msg.parts); type always JavaScript(object)
                        unit["output_ports"] = [{"name": paths[0], "type": _NODE_RED_MSG_TYPE}]
                    else:
                        unit["output_ports"] = [{"name": "msg.payload", "type": _NODE_RED_MSG_TYPE}]
                else:
                    unit["output_ports"] = [{"name": "msg.payload", "type": _NODE_RED_MSG_TYPE}]
            elif isinstance(raw_type, str) and raw_type.lower() == "trigger":
                trigger_ports = _node_red_trigger_output_ports(n, 1)
                unit["output_ports"] = trigger_ports if trigger_ports else [{"name": "msg.payload", "type": _NODE_RED_MSG_TYPE}]
            else:
                unit["output_ports"] = [{"name": "msg.payload", "type": _NODE_RED_MSG_TYPE}]
        elif num_out > 1:
            port_specs: list[dict[str, str]] | None = None
            if isinstance(raw_type, str) and raw_type.lower() == "switch":
                port_specs = _node_red_switch_output_ports(n, num_out)
            elif isinstance(raw_type, str) and raw_type.lower() == "trigger":
                port_specs = _node_red_trigger_output_ports(n, num_out)
            if port_specs is not None:
                unit["output_ports"] = port_specs
            else:
                port_names = [str(i) for i in range(num_out)]
                if raw_type == "function":
                    func_src = n.get("func") or ""
                    if isinstance(func_src, str):
                        paths = _node_red_parse_msg_property_paths(func_src)
                        if paths:
                            port_names = [
                                paths[i] if i < len(paths) else "msg.payload"
                                for i in range(num_out)
                            ]
                        else:
                            port_names = ["msg.payload"] * num_out
                unit["output_ports"] = [{"name": name, "type": _NODE_RED_MSG_TYPE} for name in port_names]
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
    # Resolve input_ports from node "inputs" property (21-mqtt_spec: inputs 0 = source, 1 = one msg port)
    # When inputs is absent, infer from incoming connections (backward compatibility)
    to_ids_with_input: set[str] = {c["to"] for c in connections}
    for u in units:
        params = u.get("params") or {}
        num_in = params.get("inputs")
        if num_in is not None:
            try:
                n = int(num_in)
                if n == 0:
                    u["input_ports"] = []
                else:
                    u["input_ports"] = [{"name": "msg", "type": _NODE_RED_MSG_TYPE} for _ in range(n)]
            except (TypeError, ValueError):
                if u["id"] in to_ids_with_input:
                    u["input_ports"] = [{"name": "msg", "type": _NODE_RED_MSG_TYPE}]
        elif u["id"] in to_ids_with_input:
            u["input_ports"] = [{"name": "msg", "type": _NODE_RED_MSG_TYPE}]
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
