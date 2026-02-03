"""
Inject an RL Agent node into a Node-RED / EdgeLinkd flow (list or dict of nodes).

The flow must be in a format we can normalize to a list of nodes (array of nodes,
or { nodes: [] }, or { flows: [ { nodes: [] } ] }). We add one node (type RLAgent,
id = agent_id, params.model_path, wires to action targets) and add wires from
observation_source_ids to the agent node.
"""
from typing import Any


def _nodes_list(flow: dict | list) -> list[dict[str, Any]]:
    """Return mutable list of node dicts from flow (array, or flow with nodes/flows)."""
    if isinstance(flow, list):
        return list(flow)
    if isinstance(flow, dict):
        nodes = flow.get("nodes")
        if nodes is not None:
            return list(nodes)
        flows = flow.get("flows")
        if isinstance(flows, list) and flows and isinstance(flows[0], dict) and "nodes" in flows[0]:
            return list(flows[0]["nodes"])
    return []


def _put_back(flow: dict | list, nodes: list[dict[str, Any]]) -> dict | list:
    """Put nodes back into the same structure as flow."""
    if isinstance(flow, list):
        return nodes
    if isinstance(flow, dict):
        if "nodes" in flow:
            out = dict(flow)
            out["nodes"] = nodes
            return out
        flows = flow.get("flows")
        if isinstance(flows, list) and flows and isinstance(flows[0], dict):
            out = dict(flow)
            out["flows"] = [{**flows[0], "nodes": nodes}] + flows[1:]
            return out
    return nodes


def inject_agent_into_flow(
    flow: dict | list,
    agent_id: str,
    model_path: str,
    observation_source_ids: list[str],
    action_target_ids: list[str],
    *,
    agent_type: str = "RLAgent",
) -> dict | list:
    """
    Add an RL Agent node to the flow and wire it to observations (inputs) and actions (outputs).

    Args:
        flow: Node-RED/EdgeLinkd flow (list of nodes, or { nodes: [] }, or { flows: [ { nodes: [] } ] }).
        agent_id: Unique id for the new agent node (e.g. "temperature_controller").
        model_path: Path to the trained model (e.g. "models/temperature_controller/best/best_model.zip").
        observation_source_ids: Node ids that send observations into the agent (e.g. ["thermometer"]).
        action_target_ids: Node ids that receive actions from the agent (e.g. ["hot_valve", "cold_valve", "dump_valve"]).
        agent_type: Unit type for the agent node (default "RLAgent").

    Returns:
        New flow (same structure as input) with the agent node and wires added.
    """
    nodes = _nodes_list(flow)
    if not nodes:
        return _put_back(flow, nodes)

    # Ensure agent_id is not already present
    existing_ids = {n.get("id") or n.get("name") for n in nodes if isinstance(n, dict)}
    if agent_id in existing_ids:
        raise ValueError(f"Flow already contains a node with id {agent_id}")

    # Add wires from observation sources to the agent (append agent_id to each source's first output)
    source_ids = set(observation_source_ids)
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("id") or n.get("name")
        if nid not in source_ids:
            continue
        wires = list(n.get("wires") or [])
        if not wires:
            wires = [[]]
        else:
            wires = [list(w) for w in wires]
        if agent_id not in wires[0]:
            wires[0].append(agent_id)
        n["wires"] = wires

    # Create the agent node: inputs from observation sources, output to action targets
    agent_node: dict[str, Any] = {
        "id": agent_id,
        "type": agent_type,
        "wires": [list(action_target_ids)],
        "params": {"model_path": model_path},
    }
    nodes.append(agent_node)

    return _put_back(flow, nodes)


# --- PyFlow flow injection ---


def _pyflow_nodes_list_mutable(flow: dict) -> list:
    """Return mutable list of nodes from a PyFlow graph dict; may be top-level or under graphs[0]."""
    nodes = flow.get("nodes")
    if isinstance(nodes, list):
        return nodes
    graphs = flow.get("graphs")
    if isinstance(graphs, list) and graphs and isinstance(graphs[0], dict):
        nodes = graphs[0].get("nodes")
        if isinstance(nodes, list):
            return nodes
    gm = flow.get("graphManager") or flow.get("graph_manager")
    if isinstance(gm, dict):
        graphs = gm.get("graphs")
        if isinstance(graphs, list) and graphs and isinstance(graphs[0], dict):
            nodes = graphs[0].get("nodes")
            if isinstance(nodes, list):
                return nodes
    return []


def _pyflow_connections_list_mutable(flow: dict) -> list:
    """Return mutable list of connection dicts (from/to) from a PyFlow graph."""
    for key in ("connections", "edges", "wires"):
        conns = flow.get(key)
        if isinstance(conns, list):
            return conns
    graphs = flow.get("graphs")
    if isinstance(graphs, list) and graphs and isinstance(graphs[0], dict):
        for key in ("connections", "edges", "wires"):
            conns = graphs[0].get(key)
            if isinstance(conns, list):
                return conns
    gm = flow.get("graphManager") or flow.get("graph_manager")
    if isinstance(gm, dict):
        graphs = gm.get("graphs")
        if isinstance(graphs, list) and graphs and isinstance(graphs[0], dict):
            for key in ("connections", "edges", "wires"):
                conns = graphs[0].get(key)
                if isinstance(conns, list):
                    return conns
    return []


def _pyflow_conns_ensure(flow: dict) -> list:
    """Return mutable connections list; create and store under same place as nodes if missing."""
    conns = _pyflow_connections_list_mutable(flow)
    # If flow already has a connections list (any key), we got a reference to it
    for d in (flow,):
        if d.get("connections") is conns or d.get("edges") is conns or d.get("wires") is conns:
            return conns
    graphs = flow.get("graphs")
    if isinstance(graphs, list) and graphs and isinstance(graphs[0], dict):
        if graphs[0].get("connections") is conns or graphs[0].get("edges") is conns or graphs[0].get("wires") is conns:
            return conns
        graphs[0]["connections"] = list(conns)
        return graphs[0]["connections"]
    gm = flow.get("graphManager") or flow.get("graph_manager")
    if isinstance(gm, dict) and gm.get("graphs") and isinstance(gm["graphs"][0], dict):
        g0 = gm["graphs"][0]
        if g0.get("connections") is conns or g0.get("edges") is conns or g0.get("wires") is conns:
            return conns
        g0["connections"] = list(conns)
        return g0["connections"]
    flow["connections"] = list(conns)
    return flow["connections"]


def inject_agent_into_pyflow_flow(
    flow: dict,
    agent_id: str,
    model_path: str,
    observation_source_ids: list[str],
    action_target_ids: list[str],
    *,
    agent_type: str = "RLAgent",
) -> dict:
    """
    Add an RL Agent node to a PyFlow graph and wire it to observations (inputs) and actions (outputs).

    The flow must be a PyFlow-style dict: top-level or graphs[0] / graphManager.graphs[0] with
    "nodes" (list) and "connections" / "edges" / "wires" (list of { "from", "to" } or { "from_id", "to_id" }).

    Args:
        flow: PyFlow graph dict (nodes + connections at top level or under graphs[0]).
        agent_id: Unique id for the new agent node.
        model_path: Path to the trained model (e.g. models/<agent>/best/best_model.zip).
        observation_source_ids: Node ids that send observations into the agent.
        action_target_ids: Node ids that receive actions from the agent.
        agent_type: Unit type for the agent node (default "RLAgent").

    Returns:
        The same flow dict with the agent node and new connections added (mutates in place and returns flow).
    """
    nodes = _pyflow_nodes_list_mutable(flow)
    if not nodes:
        if flow.get("graphs") and isinstance(flow["graphs"][0], dict):
            flow["graphs"][0]["nodes"] = []
            nodes = flow["graphs"][0]["nodes"]
        elif flow.get("graphManager") and flow["graphManager"].get("graphs") and flow["graphManager"]["graphs"][0]:
            flow["graphManager"]["graphs"][0]["nodes"] = []
            nodes = flow["graphManager"]["graphs"][0]["nodes"]
        else:
            flow["nodes"] = []
            nodes = flow["nodes"]

    existing_ids = {str(n.get("id") or n.get("name") or n.get("uuid") or "") for n in nodes if isinstance(n, dict)}
    if agent_id in existing_ids:
        raise ValueError(f"PyFlow flow already contains a node with id {agent_id}")

    conns = _pyflow_conns_ensure(flow)

    agent_node: dict[str, Any] = {
        "id": agent_id,
        "name": agent_id,
        "type": agent_type,
        "params": {"model_path": model_path, "agent_id": agent_id},
    }
    nodes.append(agent_node)

    for src in observation_source_ids:
        conns.append({"from": src, "to": agent_id})
    for tgt in action_target_ids:
        conns.append({"from": agent_id, "to": tgt})

    return flow


# --- n8n flow injection ---


def _n8n_connections_ensure(flow: dict) -> dict:
    """Return mutable connections object; create if missing."""
    conns = flow.get("connections")
    if isinstance(conns, dict):
        return conns
    flow["connections"] = {}
    return flow["connections"]


def inject_agent_into_n8n_flow(
    flow: dict,
    agent_id: str,
    model_path: str,
    observation_source_ids: list[str],
    action_target_ids: list[str],
    *,
    agent_type: str = "RLAgent",
    position: tuple[float, float] = (500, 300),
) -> dict:
    """
    Add an RL Agent node to an n8n workflow and wire it (observations in, actions out).

    n8n connections are keyed by **node name**: { "SourceName": { "main": [[ { "node": "TargetName", "type": "main", "index": 0 } ]] } }.
    observation_source_ids and action_target_ids are node **names** (as in the n8n flow).

    Args:
        flow: n8n workflow dict (nodes array + connections object).
        agent_id: Unique id and name for the new agent node.
        model_path: Path to the trained model (e.g. models/<agent>/best/best_model.zip).
        observation_source_ids: Node names that send observations into the agent.
        action_target_ids: Node names that receive actions from the agent.
        agent_type: Node type for the agent (default "RLAgent"); use a custom n8n node type if you have one.
        position: [x, y] on canvas (default (500, 300)).

    Returns:
        The same flow dict with the agent node and connections updated (mutates in place and returns flow).
    """
    nodes = flow.get("nodes")
    if not isinstance(nodes, list):
        flow["nodes"] = []
        nodes = flow["nodes"]

    existing = {str(n.get("name") or n.get("id") or "") for n in nodes if isinstance(n, dict)}
    if agent_id in existing:
        raise ValueError(f"n8n flow already contains a node with name/id {agent_id}")

    conns = _n8n_connections_ensure(flow)
    agent_connection = {"node": agent_id, "type": "main", "index": 0}

    # Wire observation sources → agent (add agent as target of each source's main output)
    for src_name in observation_source_ids:
        if not src_name:
            continue
        if src_name not in conns:
            conns[src_name] = {}
        main_out = conns[src_name].get("main")
        if not isinstance(main_out, list):
            main_out = []
            conns[src_name]["main"] = main_out
        if len(main_out) == 0:
            main_out.append([])
        main_out[0].append(dict(agent_connection))

    # Agent node: one output → all action targets
    conns[agent_id] = {
        "main": [[{"node": t, "type": "main", "index": 0} for t in action_target_ids]],
    }

    agent_node: dict[str, Any] = {
        "id": agent_id,
        "name": agent_id,
        "type": agent_type,
        "typeVersion": 1,
        "position": list(position),
        "parameters": {"model_path": model_path},
    }
    nodes.append(agent_node)

    return flow
