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
