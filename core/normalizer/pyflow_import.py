"""PyFlow graph import: map PyFlow graph JSON to canonical process graph dict."""
import copy
from typing import Any

from core.normalizer.shared import _ensure_list_connections
# Keys used for graph structure / identity; do not store in unit.params.
_PYFLOW_STRUCTURE_KEYS = frozenset({"id", "name", "type", "uuid", "nodeType", "__class__"})


def _pyflow_nodes_list(raw: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = raw.get("nodes")
    if isinstance(nodes, list):
        return nodes
    graphs = raw.get("graphs")
    if isinstance(graphs, list) and graphs and isinstance(graphs[0], dict):
        n = graphs[0].get("nodes")
        if isinstance(n, list):
            return n
    gm = raw.get("graphManager") or raw.get("graph_manager")
    if isinstance(gm, dict):
        graphs = gm.get("graphs")
        if isinstance(graphs, list) and graphs and isinstance(graphs[0], dict):
            n = graphs[0].get("nodes")
            if isinstance(n, list):
                return n
    return []


def _pyflow_connections_list(raw: dict[str, Any], node_ids: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    conns = raw.get("connections") or raw.get("edges") or raw.get("wires")
    if not isinstance(conns, list):
        graphs = raw.get("graphs")
        if isinstance(graphs, list) and graphs and isinstance(graphs[0], dict):
            conns = graphs[0].get("connections") or graphs[0].get("edges") or graphs[0].get("wires")
    if isinstance(conns, list):
        for c in conns:
            if not isinstance(c, dict):
                continue
            from_id = c.get("from") or c.get("from_id") or c.get("out") or c.get("source")
            to_id = c.get("to") or c.get("to_id") or c.get("in") or c.get("target")
            if from_id is None or to_id is None:
                continue
            from_id, to_id = str(from_id), str(to_id)
            from_port = str(c.get("from_port") or c.get("from_slot") or "0")
            to_port = str(c.get("to_port") or c.get("to_slot") or "0")
            if ":" in from_id:
                from_id = from_id.split(":")[0]
            if ":" in to_id:
                to_id = to_id.split(":")[0]
            if from_id in node_ids and to_id in node_ids:
                out.append({"from": from_id, "to": to_id, "from_port": from_port, "to_port": to_port})
    return out


def to_canonical_dict(raw: dict[str, Any]) -> dict[str, Any]:
    nodes = _pyflow_nodes_list(raw)
    env_type = str(raw.get("environment_type", raw.get("process_environment_type", "thermodynamic")))
    unit_ids: set[str] = set()
    units: list[dict[str, Any]] = []
    code_blocks: list[dict[str, Any]] = []

    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("id") or n.get("name") or n.get("uuid")
        if nid is None:
            continue
        nid = str(nid)
        ntype = n.get("type") or n.get("nodeType") or n.get("__class__") or n.get("name") or "Node"
        if isinstance(ntype, dict):
            ntype = ntype.get("name", "Node")
        ntype = str(ntype).split(".")[-1]
        unit_ids.add(nid)
        # Preserve all PyFlow node keys as params (params, data, payload, pins, x, y, etc.)
        params: dict[str, Any] = {}
        for key, val in n.items():
            if key in _PYFLOW_STRUCTURE_KEYS or val is None:
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
        unit_py: dict[str, Any] = {"id": nid, "type": ntype, "controllable": controllable, "params": params}
        py_name = n.get("name") or n.get("title")
        if isinstance(py_name, str) and py_name.strip():
            unit_py["name"] = py_name.strip()
        units.append(unit_py)
        source = n.get("code") or n.get("script") or n.get("source") or n.get("expression")
        if source is not None and isinstance(source, str) and source.strip():
            code_blocks.append({"id": nid, "language": str(n.get("language", "python")), "source": source})

    connections = _pyflow_connections_list(raw, unit_ids)
    if not connections and nodes:
        for n in nodes:
            if not isinstance(n, dict):
                continue
            from_id = str(n.get("id") or n.get("name") or "")
            if from_id not in unit_ids:
                continue
            pins = n.get("pins") or []
            for out_idx, pin in enumerate(pins if isinstance(pins, list) else []):
                if not isinstance(pin, dict):
                    continue
                links = pin.get("connections") or pin.get("links") or pin.get("wires") or []
                for link in links if isinstance(links, list) else []:
                    to_id = link if isinstance(link, str) else (link.get("to") or link.get("node") or link.get("target"))
                    if to_id is None:
                        continue
                    to_id = str(to_id)
                    if ":" in to_id:
                        to_id = to_id.split(":")[0]
                    if to_id in unit_ids and to_id != from_id:
                        to_port = str(link.get("index", link.get("to_slot", 0))) if isinstance(link, dict) else "0"
                        connections.append({"from": from_id, "to": to_id, "from_port": str(out_idx), "to_port": to_port})
    seen: set[tuple[str, str]] = set()
    unique_conns: list[dict[str, str]] = []
    for c in connections:
        key = (c["from"], c["to"])
        if key not in seen:
            seen.add(key)
            unique_conns.append(c)
    connections = unique_conns

    result: dict[str, Any] = {
        "environment_type": env_type,
        "units": units,
        "connections": _ensure_list_connections(connections) if connections else [],
    }
    if code_blocks:
        result["code_blocks"] = code_blocks
    layout: dict[str, dict[str, float]] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("id") or n.get("name") or n.get("uuid")
        if nid is None or str(nid) not in unit_ids:
            continue
        nid = str(nid)
        x, y = n.get("x"), n.get("y")
        if x is not None and y is not None:
            try:
                layout[nid] = {"x": float(x), "y": float(y)}
            except (TypeError, ValueError):
                pass
        else:
            pos = n.get("position") or n.get("pos")
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                try:
                    layout[nid] = {"x": float(pos[0]), "y": float(pos[1])}
                except (TypeError, ValueError):
                    pass
            elif isinstance(pos, dict) and "x" in pos and "y" in pos:
                try:
                    layout[nid] = {"x": float(pos["x"]), "y": float(pos["y"])}
                except (TypeError, ValueError):
                    pass
    if layout:
        result["layout"] = layout
    result["origin"] = {"pyflow": {}}
    return result
