"""
Inject an RL Agent node into a Node-RED / EdgeLinkd flow (list or dict of nodes).

The flow must be in a format we can normalize to a list of nodes (array of nodes,
or { nodes: [] }, or { flows: [ { nodes: [] } ] }). We add one node (type RLAgent,
id = agent_id, params.model_path, wires to action targets) and add wires from
observation_source_ids to the agent node.

PyFlow: Agent node includes template-based Python code_block (HTTP client to
inference service). Run: python -m server.inference_server --model <path>
"""
from typing import Any

from deploy.agent_inject import (
    render_llm_agent_predict_js,
    render_llm_agent_predict_n8n,
    render_llm_agent_predict_py,
    render_rl_agent_predict_py,
)


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


def _infer_flow_id(flow: dict | list) -> str:
    """Infer Node-RED flow/tab id from first node that has z."""
    nodes = _nodes_list(flow)
    for n in nodes:
        if isinstance(n, dict) and n.get("z") is not None:
            return str(n["z"])
    return "flow_main"


def inject_llm_agent_into_flow(
    flow: dict | list,
    agent_id: str,
    observation_source_ids: list[str],
    action_target_ids: list[str],
    *,
    inference_url: str = "http://127.0.0.1:8001/predict",
    system_prompt: str = "You are a control agent. Output JSON with 'action' key (list of numbers).",
    user_prompt_template: str = "Observations: {observation_json}. Output only JSON with key 'action'.",
    model_name: str = "llama3.2",
    provider: str = "ollama",
    host: str = "",
) -> dict | list:
    """
    Add an LLMAgent function node to a Node-RED/EdgeLinkd flow and wire it.
    Run: python -m server.llm_inference_server --port 8001
    """
    nodes = _nodes_list(flow)
    if not nodes:
        return _put_back(flow, nodes)
    existing = {n.get("id") or n.get("name") for n in nodes if isinstance(n, dict)}
    if agent_id in existing:
        raise ValueError(f"Flow already contains node {agent_id}")
    flow_id = _infer_flow_id(flow)
    code_src = render_llm_agent_predict_js(
        inference_url, observation_source_ids,
        system_prompt, user_prompt_template, model_name, provider, host,
    )
    agent_node: dict[str, Any] = {
        "id": agent_id,
        "type": "function",
        "z": flow_id,
        "name": "LLMAgent",
        "func": code_src,
        "outputs": 1,
        "noerr": 0,
        "wires": [list(action_target_ids)],
    }
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("id") or n.get("name")
        if nid not in observation_source_ids:
            continue
        wires = list(n.get("wires") or [])
        if not wires:
            wires = [[]]
        else:
            wires = [list(w) for w in wires]
        if agent_id not in wires[0]:
            wires[0].append(agent_id)
        n["wires"] = wires
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
    inference_url: str = "http://127.0.0.1:8000/predict",
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

    code_src = render_rl_agent_predict_py(inference_url, observation_source_ids)
    agent_node: dict[str, Any] = {
        "id": agent_id,
        "name": agent_id,
        "type": agent_type,
        "params": {"model_path": model_path, "agent_id": agent_id},
        "code": code_src,
    }
    nodes.append(agent_node)

    for src in observation_source_ids:
        conns.append({"from": src, "to": agent_id})
    for tgt in action_target_ids:
        conns.append({"from": agent_id, "to": tgt})

    return flow


def inject_llm_agent_into_pyflow_flow(
    flow: dict,
    agent_id: str,
    observation_source_ids: list[str],
    action_target_ids: list[str],
    *,
    inference_url: str = "http://127.0.0.1:8001/predict",
    system_prompt: str = "You are a control agent. Output JSON with 'action' key (list of numbers).",
    user_prompt_template: str = "Observations: {observation_json}. Output only JSON with key 'action'.",
    model_name: str = "llama3.2",
    provider: str = "ollama",
    host: str = "",
) -> dict:
    """
    Add an LLMAgent node to a PyFlow graph with Python code_block.
    Run: python -m server.llm_inference_server --port 8001
    """
    nodes = _pyflow_nodes_list_mutable(flow)
    if not nodes:
        if flow.get("graphs") and isinstance(flow["graphs"][0], dict):
            flow["graphs"][0]["nodes"] = []
            nodes = flow["graphs"][0]["nodes"]
        elif flow.get("graphManager") and flow["graphManager"].get("graphs"):
            flow["graphManager"]["graphs"][0]["nodes"] = []
            nodes = flow["graphManager"]["graphs"][0]["nodes"]
        else:
            flow["nodes"] = []
            nodes = flow["nodes"]
    existing = {str(n.get("id") or n.get("name") or "") for n in nodes if isinstance(n, dict)}
    if agent_id in existing:
        raise ValueError(f"PyFlow flow already contains node {agent_id}")
    conns = _pyflow_conns_ensure(flow)
    code_src = render_llm_agent_predict_py(
        inference_url, observation_source_ids,
        system_prompt, user_prompt_template, model_name, provider, host,
    )
    agent_node: dict[str, Any] = {
        "id": agent_id,
        "name": agent_id,
        "type": "LLMAgent",
        "params": {"model_name": model_name, "provider": provider},
        "code": code_src,
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


def inject_llm_agent_into_n8n_flow(
    flow: dict,
    agent_id: str,
    observation_source_ids: list[str],
    action_target_ids: list[str],
    *,
    inference_url: str = "http://127.0.0.1:8001/predict",
    system_prompt: str = "You are a control agent. Output JSON with 'action' key (list of numbers).",
    user_prompt_template: str = "Observations: {observation_json}. Output only JSON with key 'action'.",
    model_name: str = "llama3.2",
    provider: str = "ollama",
    host: str = "",
    position: tuple[float, float] = (500, 300),
) -> dict:
    """
    Add an LLMAgent Code node to an n8n workflow and wire it.
    Run: python -m server.llm_inference_server --port 8001
    """
    nodes = flow.get("nodes")
    if not isinstance(nodes, list):
        flow["nodes"] = []
        nodes = flow["nodes"]
    existing = {str(n.get("name") or n.get("id") or "") for n in nodes if isinstance(n, dict)}
    if agent_id in existing:
        raise ValueError(f"n8n flow already contains node {agent_id}")
    conns = _n8n_connections_ensure(flow)
    code_src = render_llm_agent_predict_n8n(
        inference_url, observation_source_ids,
        system_prompt, user_prompt_template, model_name, provider, host,
    )
    agent_conn = {"node": agent_id, "type": "main", "index": 0}
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
        main_out[0].append(dict(agent_conn))
    conns[agent_id] = {"main": [[{"node": t, "type": "main", "index": 0} for t in action_target_ids]]}
    agent_node: dict[str, Any] = {
        "id": agent_id,
        "name": agent_id,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": list(position),
        "parameters": {"jsCode": code_src},
    }
    nodes.append(agent_node)
    return flow


def inject_agent_into_comfyui_workflow(
    workflow: dict[str, Any],
    agent_id: str,
    model_path: str,
    observation_source_ids: list[str],
    action_target_ids: list[str],
    *,
    inference_url: str = "http://127.0.0.1:8000/predict",
    position: tuple[float, float] = (500, 300),
) -> dict[str, Any]:
    """
    Add an RL Agent node (RLAgentPredict) to a ComfyUI workflow and wire it.

    Requires ComfyUI custom node RLAgentPredict to be installed.
    observation_source_ids and action_target_ids are node ids in the workflow.

    Args:
        workflow: ComfyUI workflow dict (nodes, links, state).
        agent_id: Unique id for the agent node.
        model_path: Path to trained model (for docs; server loads it).
        observation_source_ids: Node ids that send observations into the agent.
        action_target_ids: Node ids that receive actions from the agent.
        inference_url: URL of the inference server.
        position: [x, y] on canvas.

    Returns:
        workflow with agent node and links added (mutates in place).
    """
    from deploy.oracle_inject import _comfyui_ensure_state

    state = _comfyui_ensure_state(workflow)
    next_node_id = int(state.get("lastNodeId", 0)) + 1
    next_link_id = int(state.get("lastLinkId", 0)) + 1

    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        workflow["nodes"] = []
        nodes = workflow["nodes"]
    links = workflow.get("links")
    if not isinstance(links, list):
        workflow["links"] = []
        links = workflow["links"]

    node_ids = {str(n.get("id")) for n in nodes if isinstance(n, dict) and n.get("id") is not None}
    if agent_id in node_ids:
        raise ValueError(f"ComfyUI workflow already contains node {agent_id}")

    x, y = position
    agent_node_id = next_node_id
    next_node_id += 1

    # Links: obs_sources -> agent
    agent_input_links: list[int] = []
    for src_id in observation_source_ids:
        if src_id not in node_ids:
            continue
        lid = next_link_id
        next_link_id += 1
        links.append({
            "id": lid,
            "origin_id": src_id,
            "origin_slot": 0,
            "target_id": agent_node_id,
            "target_slot": len(agent_input_links),
            "type": "FLOAT",
        })
        agent_input_links.append(lid)
        for n in nodes:
            if isinstance(n, dict) and str(n.get("id")) == src_id:
                outs = n.get("outputs") or []
                if not outs:
                    n["outputs"] = [{"name": "output_0", "type": "FLOAT", "links": [lid]}]
                else:
                    out0 = outs[0] if outs else {}
                    out_links = list(out0.get("links") or [])
                    out_links.append(lid)
                    if outs:
                        outs[0] = {**out0, "links": out_links}
                break

    # Links: agent -> action_targets
    agent_output_links: list[int] = []
    for tid in action_target_ids:
        if tid not in node_ids:
            continue
        lid = next_link_id
        next_link_id += 1
        links.append({
            "id": lid,
            "origin_id": agent_node_id,
            "origin_slot": 0,
            "target_id": tid,
            "target_slot": 0,
            "type": "FLOAT",
        })
        agent_output_links.append(lid)
        for n in nodes:
            if isinstance(n, dict) and str(n.get("id")) == tid:
                ins = n.get("inputs") or []
                ins.append({"name": f"rl_action_{len(ins)}", "type": "FLOAT", "link": lid})
                n["inputs"] = ins
                break

    agent_node: dict[str, Any] = {
        "id": agent_node_id,
        "type": "RLAgentPredict",
        "pos": [x, y],
        "size": [315, 80],
        "flags": {},
        "order": len(nodes),
        "mode": 0,
        "properties": {},
        "inputs": [
            {"name": f"obs_{i}", "type": "FLOAT", "link": agent_input_links[i]}
            for i in range(len(agent_input_links))
        ],
        "outputs": [{"name": "action", "type": "FLOAT", "links": agent_output_links}],
        "widgets_values": [inference_url, model_path],
    }
    nodes.append(agent_node)
    state["lastNodeId"] = next_node_id - 1
    state["lastLinkId"] = next_link_id - 1

    return workflow
