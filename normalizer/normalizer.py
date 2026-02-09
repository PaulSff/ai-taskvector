"""
Data normalizer: map raw input (dict, YAML, Node-RED) to canonical ProcessGraph and TrainingConfig.
All external formats flow through here so the rest of the stack sees one schema.
"""
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import ValidationError

from schemas.process_graph import CodeBlock, EnvironmentType, NodePosition, ProcessGraph, Unit, Connection
from schemas.training_config import (
    EnvironmentConfig,
    TrainingConfig,
    GoalConfig,
    RewardsConfig,
    HyperparametersConfig,
    CallbacksConfig,
    RunConfig,
)

FormatProcess = Literal["yaml", "dict", "node_red", "template", "pyflow", "ryven", "idaes", "n8n"]
FormatTraining = Literal["yaml", "dict"]

# Unit types we recognize from Node-RED (custom process-unit nodes or type field)
PROCESS_UNIT_TYPES = ("Source", "Valve", "Tank", "Sensor")


def _ensure_list_connections(raw: list[Any]) -> list[dict[str, str]]:
    """Ensure each connection has 'from' and 'to' keys (normalize key names)."""
    out: list[dict[str, str]] = []
    for c in raw:
        if isinstance(c, dict):
            from_id = c.get("from") or c.get("from_id")
            to_id = c.get("to") or c.get("to_id")
            if from_id is not None and to_id is not None:
                out.append({"from": str(from_id), "to": str(to_id)})
    return out


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
            # First tab's nodes, or concatenate all
            first = flows[0]
            if isinstance(first, dict) and "nodes" in first:
                return first["nodes"]
            if isinstance(first, list):
                return first
        # Single flow object with nodes inside
        for key in ("flow", "tab"):
            tab = raw.get(key)
            if isinstance(tab, dict) and "nodes" in tab:
                return tab["nodes"]
    return []


def _node_red_to_canonical_dict(raw: dict[str, Any] | list[Any]) -> dict[str, Any]:
    """
    Map Node-RED flow JSON to canonical process graph dict (environment_type, units, connections, code_blocks).
    Full support: all nodes are included as units; all wires become connections; code from function
    (and similar) nodes is extracted into code_blocks for roundtrip and node_red_adapter use.
    - Units: every node with id/name → Unit(id, type=node.type|unitType|processType, controllable, params).
    - Connections: every wire between any two nodes (full topology).
    - code_blocks: nodes with func/code/template (e.g. function, exec) → CodeBlock(id, language, source).
    """
    nodes = _node_red_nodes_list(raw)
    env_type = "thermodynamic"
    if isinstance(raw, dict):
        env_type = str(raw.get("environment_type", raw.get("process_environment_type", env_type)))

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
        ntype = n.get("unitType") or n.get("processType") or n.get("type") or "node"
        ntype = str(ntype)
        unit_ids.add(nid)
        params = dict(n.get("params") or n.get("payload") or {})
        controllable = n.get("controllable")
        if controllable is None:
            controllable = ntype == "Valve"
        else:
            controllable = bool(controllable)
        units.append({"id": nid, "type": ntype, "controllable": controllable, "params": params})

        # Extract code for code_blocks (function node: func; exec: command; template/code nodes)
        source = n.get("func") or n.get("code") or n.get("template") or n.get("command")
        if source is not None and isinstance(source, str) and source.strip():
            lang = "shell" if ntype == "exec" else "javascript"
            code_blocks.append({"id": nid, "language": lang, "source": source})

    connections: list[dict[str, str]] = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        from_id = n.get("id") or n.get("name")
        if from_id is None:
            continue
        from_id = str(from_id)
        wires = n.get("wires") or []
        for out_ports in wires:
            if not isinstance(out_ports, list):
                continue
            for to_id in out_ports:
                if to_id is None:
                    continue
                to_id = str(to_id)
                if to_id in unit_ids:
                    connections.append({"from": from_id, "to": to_id})

    result: dict[str, Any] = {
        "environment_type": env_type,
        "units": units,
        "connections": connections,
    }
    if code_blocks:
        result["code_blocks"] = code_blocks
    # Layout from Node-RED node x, y (flow nodes have x/y; config/tab nodes may not)
    layout: dict[str, dict[str, float]] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("id") or n.get("name")
        if nid is None:
            continue
        x, y = n.get("x"), n.get("y")
        if x is not None and y is not None and nid in unit_ids:
            try:
                layout[str(nid)] = {"x": float(x), "y": float(y)}
            except (TypeError, ValueError):
                pass
    if layout:
        result["layout"] = layout
    return result


def _pyflow_nodes_list(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract flat list of nodes from PyFlow graph (GraphManager.graphs[].nodes or raw['nodes'])."""
    nodes = raw.get("nodes")
    if isinstance(nodes, list):
        return nodes
    graphs = raw.get("graphs")
    if isinstance(graphs, list) and graphs:
        first = graphs[0]
        if isinstance(first, dict):
            n = first.get("nodes")
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


def _pyflow_connections_list(raw: dict[str, Any], node_ids: set[str]) -> list[dict[str, str]]:
    """Extract connections from PyFlow (raw['connections'] or graph connections). Normalize to node id -> node id."""
    out: list[dict[str, str]] = []
    # Top-level connections
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
            # If pin refs (e.g. "nodeId:pinName"), take node id part
            if ":" in from_id:
                from_id = from_id.split(":")[0]
            if ":" in to_id:
                to_id = to_id.split(":")[0]
            if from_id in node_ids and to_id in node_ids:
                out.append({"from": from_id, "to": to_id})
    return out


def _pyflow_to_canonical_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Map PyFlow graph JSON to canonical process graph dict (environment_type, units, connections, code_blocks).
    PyFlow layout: GraphManager → graphs → nodes (→ pins). We map each node to a Unit; node type can be
    process-unit (Source, Valve, Tank, Sensor) or generic; we accept all and preserve type. Script/code
    in nodes is extracted into code_blocks. See docs/WORKFLOW_EDITORS_AND_CODE.md.
    """
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
        ntype = str(ntype).split(".")[-1]  # e.g. "PyFlow.Packages.Foo.Valve" -> "Valve"
        unit_ids.add(nid)
        params = dict(n.get("params") or n.get("data") or n.get("payload") or {})
        controllable = n.get("controllable")
        if controllable is None:
            controllable = ntype == "Valve"
        else:
            controllable = bool(controllable)
        units.append({"id": nid, "type": ntype, "controllable": controllable, "params": params})

        # Extract code for code_blocks (script/compound/code nodes)
        source = n.get("code") or n.get("script") or n.get("source") or n.get("expression")
        if source is not None and isinstance(source, str) and source.strip():
            code_blocks.append({
                "id": nid,
                "language": str(n.get("language", "python")),
                "source": source,
            })

    connections = _pyflow_connections_list(raw, unit_ids)
    if not connections and nodes:
        # Fallback: build from pins' connections if present on nodes
        for n in nodes:
            if not isinstance(n, dict):
                continue
            from_id = str(n.get("id") or n.get("name") or "")
            if from_id not in unit_ids:
                continue
            pins = n.get("pins") or []
            for pin in pins if isinstance(pins, list) else []:
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
                        connections.append({"from": from_id, "to": to_id})
    # Dedupe connections (from pin fallback may repeat)
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
    # Layout from PyFlow node x,y or position
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
    return result


def _template_to_canonical_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Map template-style dict to canonical process graph dict (Phase 5.2).
    Accepts: blocks (list of {id, type, params?, controllable?}) and links (list of {from, to}),
    or canonical-like units/connections. Optional template_type ("generic" | "pc_gym" | "idaes")
    and environment_type. PC-Gym/IDAES-specific mapping can be extended when schemas are defined.
    """
    env_type = str(raw.get("environment_type", raw.get("process_environment_type", "thermodynamic")))
    blocks = raw.get("blocks") or raw.get("units")
    links = raw.get("links") or raw.get("connections")
    if blocks is None:
        blocks = []
    if links is None:
        links = []
    units: list[dict[str, Any]] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        uid = b.get("id") or b.get("name")
        if uid is None:
            continue
        utype = b.get("type") or b.get("unitType") or b.get("blockType")
        if utype is None:
            continue
        units.append({
            "id": str(uid),
            "type": str(utype),
            "controllable": bool(b.get("controllable", b.get("is_control", False))),
            "params": dict(b.get("params") or b.get("parameters") or {}),
        })
    connections = _ensure_list_connections(links)
    return {
        "environment_type": env_type,
        "units": units,
        "connections": connections,
    }


def _n8n_nodes_list(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract nodes array from n8n workflow JSON (top-level 'nodes')."""
    nodes = raw.get("nodes")
    return nodes if isinstance(nodes, list) else []


def _n8n_connections_to_list(raw: dict[str, Any], node_names: set[str]) -> list[dict[str, str]]:
    """
    Flatten n8n connections object to list of { from, to }.
    n8n connections: { "SourceNodeName": { "main": [[ { "node": "TargetName", "type": "main", "index": 0 } ]] }, ... }.
    Uses node names (n8n connections are keyed by name).
    """
    out: list[dict[str, str]] = []
    conns = raw.get("connections")
    if not isinstance(conns, dict):
        return out
    for source_name, outputs in conns.items():
        if source_name not in node_names or not isinstance(outputs, dict):
            continue
        for _output_type, indices_list in outputs.items():
            if not isinstance(indices_list, list):
                continue
            for targets in indices_list:
                if not isinstance(targets, list):
                    continue
                for t in targets:
                    if isinstance(t, dict) and "node" in t:
                        to_name = t.get("node")
                        if to_name and to_name in node_names and to_name != source_name:
                            out.append({"from": source_name, "to": str(to_name)})
    return out


def _n8n_to_canonical_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Map n8n workflow JSON to canonical process graph dict (environment_type, units, connections, code_blocks).
    n8n format: nodes (array with id, name, type, typeVersion, position, parameters), connections (object
    keyed by node name: { "NodeName": { "main": [[ { node, type, index } ]] } }). We use node name as unit id
    so connections match. Code from Code node (n8n-nodes-base.code) parameters.jsCode → code_blocks.
    """
    nodes = _n8n_nodes_list(raw)
    env_type = str(raw.get("environment_type", raw.get("process_environment_type", "thermodynamic")))

    unit_ids: set[str] = set()
    units: list[dict[str, Any]] = []
    code_blocks: list[dict[str, Any]] = []

    for n in nodes:
        if not isinstance(n, dict):
            continue
        # n8n connections are keyed by node name; use name as id for roundtrip
        nid = n.get("name") or n.get("id")
        if nid is None:
            continue
        nid = str(nid)
        ntype = n.get("type") or "node"
        if isinstance(ntype, str) and "." in ntype:
            ntype = ntype.split(".")[-1]  # e.g. "n8n-nodes-base.code" -> "code"
        ntype = str(ntype)
        unit_ids.add(nid)
        params = dict(n.get("parameters") or {})
        controllable = n.get("controllable")
        if controllable is None:
            controllable = ntype.lower() in ("code", "switch", "if")  # heuristic; override via params
        else:
            controllable = bool(controllable)
        units.append({"id": nid, "type": ntype, "controllable": controllable, "params": params})

        # n8n Code node: parameters.jsCode (JavaScript) or parameters.code
        code_source = (n.get("parameters") or {}).get("jsCode") or (n.get("parameters") or {}).get("code")
        if code_source is not None and isinstance(code_source, str) and code_source.strip():
            code_blocks.append({"id": nid, "language": "javascript", "source": code_source})

    connections = _n8n_connections_to_list(raw, unit_ids)
    result: dict[str, Any] = {
        "environment_type": env_type,
        "units": units,
        "connections": _ensure_list_connections(connections),
    }
    if code_blocks:
        result["code_blocks"] = code_blocks
    # Layout from n8n node position [x, y]
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
    return result


def _idaes_to_canonical_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Map IDAES-style dict to canonical process graph dict.
    Accepts same shape as template: blocks/units, links/connections.
    Default environment_type is "chemical". observation_vars/action_vars are for
    training config (adapter_config), not stored on ProcessGraph.
    """
    env_type = str(raw.get("environment_type", raw.get("process_environment_type", "chemical")))
    return _template_to_canonical_dict({**raw, "environment_type": env_type})


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


def _ryven_connections_list(flow: dict[str, Any] | None, node_ids: set[str]) -> list[dict[str, str]]:
    """Extract connections from Ryven flow (connections, links, edges). Normalize to from/to node ids."""
    if flow is None:
        return []
    conns = flow.get("connections") or flow.get("links") or flow.get("edges") or flow.get("wires") or []
    if not isinstance(conns, list):
        return []
    out: list[dict[str, str]] = []
    for c in conns:
        if not isinstance(c, dict):
            continue
        from_id = c.get("from") or c.get("from_node") or c.get("from_id") or c.get("source")
        to_id = c.get("to") or c.get("to_node") or c.get("to_id") or c.get("target")
        if from_id is None or to_id is None:
            continue
        from_id, to_id = str(from_id), str(to_id)
        if ":" in from_id:
            from_id = from_id.split(":")[0]
        if ":" in to_id:
            to_id = to_id.split(":")[0]
        if from_id in node_ids and to_id in node_ids:
            out.append({"from": from_id, "to": to_id})
    return out


def _ryven_to_canonical_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Map Ryven project JSON to canonical process graph dict (environment_type, units, connections, code_blocks).
    Ryven layout: scripts[].flow with nodes and connections/links; or top-level flow/nodes.
    See docs/WORKFLOW_EDITORS_AND_CODE.md.
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
        data = n.get("data") or n.get("params") or n.get("parameters") or {}
        params = dict(data) if isinstance(data, dict) else {}
        controllable = n.get("controllable")
        if controllable is None:
            controllable = ntype in ("Valve", "Actuator", "Control")
        else:
            controllable = bool(controllable)
        units.append({"id": nid, "type": ntype, "controllable": controllable, "params": params})

        source = n.get("source") or n.get("code") or n.get("script")
        if source is None and isinstance(data, dict):
            source = data.get("source") or data.get("code")
        if source is not None and isinstance(source, str) and source.strip():
            code_blocks.append({
                "id": nid,
                "language": str(n.get("language", data.get("language", "python") if isinstance(data, dict) else "python")),
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
    return result


def to_process_graph(raw: dict[str, Any] | str | list[Any], format: FormatProcess = "dict") -> ProcessGraph:
    """
    Normalize raw input to canonical ProcessGraph.
    Use everywhere process data is loaded so consistency is guaranteed.

    Args:
        raw: Dict (canonical shape), YAML string, or flow (dict/list/JSON str) per format.
        format: "dict" | "yaml" | "node_red" | "template" | "pyflow" | "ryven" | "idaes".

    Returns:
        Validated canonical ProcessGraph.

    Raises:
        ValueError: If raw is invalid or missing required fields.
        pydantic.ValidationError: If schema validation fails.
    """
    if format == "yaml" and isinstance(raw, str):
        data: dict[str, Any] = yaml.safe_load(raw) or {}
    elif format == "dict" and isinstance(raw, dict):
        data = raw
    elif format == "node_red":
        if isinstance(raw, str):
            raw = json.loads(raw)
        data = _node_red_to_canonical_dict(raw)
    elif format == "template":
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            raise ValueError("raw for format='template' must be dict or JSON str")
        data = _template_to_canonical_dict(raw)
    elif format == "pyflow":
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            raise ValueError("raw for format='pyflow' must be dict or JSON str")
        data = _pyflow_to_canonical_dict(raw)
    elif format == "ryven":
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            raise ValueError("raw for format='ryven' must be dict or JSON str")
        data = _ryven_to_canonical_dict(raw)
    elif format == "idaes":
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            raise ValueError("raw for format='idaes' must be dict or JSON str")
        data = _idaes_to_canonical_dict(raw)
    elif format == "n8n":
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            raise ValueError("raw for format='n8n' must be dict or JSON str")
        data = _n8n_to_canonical_dict(raw)
    else:
        raise ValueError(
            "format must be 'dict', 'yaml', 'node_red', 'template', 'pyflow', 'ryven', 'idaes', or 'n8n'"
        )

    # Normalize environment_type (allow string or enum)
    env_type = data.get("environment_type", "thermodynamic")
    if isinstance(env_type, str):
        env_type = EnvironmentType(env_type.lower().strip())

    # Normalize units: list of dicts with id, type, optional controllable, optional params
    units_raw = data.get("units", [])
    units: list[Unit] = []
    for u in units_raw:
        if isinstance(u, dict):
            units.append(
                Unit(
                    id=str(u["id"]),
                    type=str(u["type"]),
                    controllable=bool(u.get("controllable", False)),
                    params=dict(u.get("params", {})),
                )
            )
        else:
            units.append(Unit.model_validate(u))

    # Normalize connections: list of {from, to}
    conn_raw = data.get("connections", [])
    connections_list = _ensure_list_connections(conn_raw)
    connections = [Connection.model_validate(c) for c in connections_list]

    # Optional code_blocks (language-agnostic: id, language, source)
    code_blocks_raw = data.get("code_blocks", [])
    code_blocks = [CodeBlock.model_validate(b) for b in code_blocks_raw] if isinstance(code_blocks_raw, list) else []

    # Optional layout (per-unit x, y from Node-RED / n8n / dict)
    layout_raw = data.get("layout")
    layout: dict[str, NodePosition] | None = None
    if isinstance(layout_raw, dict) and layout_raw:
        layout = {}
        for uid, pos in layout_raw.items():
            if isinstance(pos, dict) and "x" in pos and "y" in pos:
                try:
                    layout[str(uid)] = NodePosition(x=float(pos["x"]), y=float(pos["y"]))
                except (TypeError, ValueError):
                    pass
        layout = layout if layout else None

    return ProcessGraph(
        environment_type=env_type,
        units=units,
        connections=connections,
        code_blocks=code_blocks,
        layout=layout,
    )


def to_training_config(raw: dict[str, Any] | str, format: FormatTraining = "dict") -> TrainingConfig:
    """
    Normalize raw input to canonical TrainingConfig.
    Use everywhere training config is loaded so consistency is guaranteed.

    Args:
        raw: Either a dict (goal, rewards, algorithm, hyperparameters) or a YAML string.
        format: "dict" if raw is dict, "yaml" if raw is YAML string.

    Returns:
        Validated canonical TrainingConfig.

    Raises:
        ValueError: If raw is invalid.
        pydantic.ValidationError: If schema validation fails.
    """
    if format == "yaml" and isinstance(raw, str):
        data: dict[str, Any] = yaml.safe_load(raw) or {}
    elif format == "dict" and isinstance(raw, dict):
        data = raw
    else:
        raise ValueError("raw must be dict (format='dict') or YAML str (format='yaml')")

    goal_raw = data.get("goal", {})
    if isinstance(goal_raw, dict):
        goal = GoalConfig(
            type=str(goal_raw.get("type", "setpoint")),
            target_temp=goal_raw.get("target_temp"),
            target_volume_ratio=tuple(goal_raw["target_volume_ratio"]) if goal_raw.get("target_volume_ratio") else None,
            target_pressure_range=tuple(goal_raw["target_pressure_range"]) if goal_raw.get("target_pressure_range") else None,
        )
    else:
        goal = GoalConfig.model_validate(goal_raw)

    rewards_raw = data.get("rewards", {})
    if isinstance(rewards_raw, dict):
        rewards = RewardsConfig(
            preset=str(rewards_raw.get("preset", "temperature_and_volume")),
            weights=dict(rewards_raw.get("weights", {})),
        )
    else:
        rewards = RewardsConfig.model_validate(rewards_raw)

    hyper_raw = data.get("hyperparameters", {})
    if isinstance(hyper_raw, dict):
        hyperparameters = HyperparametersConfig(
            learning_rate=float(hyper_raw.get("learning_rate", 3e-4)),
            n_steps=int(hyper_raw.get("n_steps", 2048)),
            batch_size=int(hyper_raw.get("batch_size", 64)),
            n_epochs=int(hyper_raw.get("n_epochs", 10)),
            gamma=float(hyper_raw.get("gamma", 0.99)),
            gae_lambda=float(hyper_raw.get("gae_lambda", 0.95)),
            clip_range=float(hyper_raw.get("clip_range", 0.2)),
            ent_coef=float(hyper_raw.get("ent_coef", 0.01)),
        )
    else:
        hyperparameters = HyperparametersConfig.model_validate(hyper_raw)

    callbacks_raw = data.get("callbacks", {})
    if isinstance(callbacks_raw, dict):
        model_dir = callbacks_raw.get("model_dir")
        if model_dir:
            base = str(model_dir).rstrip("/")
            name_prefix = str(callbacks_raw.get("name_prefix", "ppo_temp_control"))
            callbacks = CallbacksConfig(
                eval_freq=int(callbacks_raw.get("eval_freq", 5000)),
                save_freq=int(callbacks_raw.get("save_freq", 10000)),
                model_dir=base,
                save_path=f"{base}/checkpoints/",
                name_prefix=name_prefix,
                best_model_save_path=f"{base}/best/",
                log_path=f"{base}/logs/eval/",
                tensorboard_log=f"{base}/logs/tensorboard/",
                final_model_save_path=f"{base}/{name_prefix}_final",
            )
        else:
            callbacks = CallbacksConfig(
                eval_freq=int(callbacks_raw.get("eval_freq", 5000)),
                save_freq=int(callbacks_raw.get("save_freq", 10000)),
                save_path=str(callbacks_raw.get("save_path", "./models/checkpoints/")),
                name_prefix=str(callbacks_raw.get("name_prefix", "ppo_temp_control")),
                best_model_save_path=str(callbacks_raw.get("best_model_save_path", "./models/best/")),
                log_path=str(callbacks_raw.get("log_path", "./logs/eval/")),
                tensorboard_log=str(callbacks_raw.get("tensorboard_log", "./logs/tensorboard/")),
                final_model_save_path=str(callbacks_raw.get("final_model_save_path", "./models/ppo_temperature_control_final")),
            )
    else:
        callbacks = CallbacksConfig.model_validate(callbacks_raw)

    run_raw = data.get("run", {})
    if isinstance(run_raw, dict):
        run = RunConfig(
            n_envs=int(run_raw.get("n_envs", 4)),
            randomize_params=bool(run_raw.get("randomize_params", True)),
            verbose=int(run_raw.get("verbose", 1)),
            test_episodes=int(run_raw.get("test_episodes", 5)),
        )
    else:
        run = RunConfig.model_validate(run_raw)

    total_timesteps = int(data.get("total_timesteps", 100000))

    env_raw = data.get("environment", {})
    if isinstance(env_raw, dict):
        environment = EnvironmentConfig(
            source=str(env_raw.get("source", "custom")),
            type=str(env_raw.get("type", "thermodynamic")),
            process_graph_path=env_raw.get("process_graph_path"),
            adapter=env_raw.get("adapter"),
            adapter_config=dict(env_raw.get("adapter_config") or env_raw.get("config") or {}),
            env_id=env_raw.get("env_id"),
            env_kwargs=dict(env_raw.get("env_kwargs") or env_raw.get("kwargs") or {}),
        )
    else:
        environment = EnvironmentConfig.model_validate(env_raw)

    return TrainingConfig(
        environment=environment,
        goal=goal,
        rewards=rewards,
        algorithm=str(data.get("algorithm", "PPO")),
        hyperparameters=hyperparameters,
        total_timesteps=total_timesteps,
        run=run,
        callbacks=callbacks,
    )


def load_process_graph_from_file(path: str | Path, format: FormatProcess | None = None) -> ProcessGraph:
    """Load and normalize process graph from a file. Use everywhere for consistency.
    format: None = infer from suffix (.yaml/.yml → yaml, .json → node_red), or explicit 'yaml'|'dict'|'node_red'|'template'|'pyflow'|'ryven'|'n8n'.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Process config file not found: {path}")
    text = path.read_text()
    if format is None:
        suffix = path.suffix.lower()
        format = "node_red" if suffix == ".json" else "yaml"
    if format == "dict":
        return to_process_graph(json.loads(text), format="dict")
    return to_process_graph(text, format=format)


def load_training_config_from_file(path: str | Path) -> TrainingConfig:
    """Load and normalize training config from a YAML file. Use everywhere for consistency."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Training config file not found: {path}")
    text = path.read_text()
    return to_training_config(text, format="yaml")
