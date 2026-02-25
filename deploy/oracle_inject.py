"""
Inject RLOracle (step handler) into Node-RED flows and ProcessGraph.

Universal, environment-agnostic Oracle. All parameters from training config (adapter_config).
No embedded simulations. Uses template-based step driver + collector.
See docs/DEPLOYMENT_NODERED.md.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from schemas.external_io_spec import ExternalIOSpec
from schemas.process_graph import CodeBlock, Connection, ProcessGraph, Unit

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _load_template(name: str) -> str:
    """Load template source by name."""
    path = _TEMPLATES_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Oracle template not found: {path}")
    return path.read_text()


def _render_step_driver(
    observation_names: list[str],
    action_names: list[str],
    obs_context_prefix: str = "obs_",
    step_count_key: str = "step_count",
) -> str:
    """Render step driver template."""
    template = _load_template("rloracle_step_driver.js")
    return (
        template.replace("__TPL_OBS_NAMES__", json.dumps(observation_names))
        .replace("__TPL_ACT_NAMES__", json.dumps(action_names))
        .replace("__TPL_OBS_PREFIX__", json.dumps(obs_context_prefix))
        .replace("__TPL_STEP_KEY__", json.dumps(step_count_key))
    )


def _render_collector(
    observation_names: list[str],
    reward_config: dict[str, Any],
    max_steps: int = 600,
    obs_context_prefix: str = "obs_",
    step_count_key: str = "step_count",
) -> str:
    """Render collector template."""
    template = _load_template("rloracle_collector.js")
    return (
        template.replace("__TPL_OBS_NAMES__", json.dumps(observation_names))
        .replace("__TPL_REWARD__", json.dumps(reward_config or {}))
        .replace("__TPL_MAX_STEPS__", str(max_steps))
        .replace("__TPL_OBS_PREFIX__", json.dumps(obs_context_prefix))
        .replace("__TPL_STEP_KEY__", json.dumps(step_count_key))
    )


def _render_step_driver_n8n(
    observation_names: list[str],
    action_names: list[str],
    obs_context_prefix: str = "obs_",
    step_count_key: str = "step_count",
) -> str:
    """Render n8n step driver template (uses $getWorkflowStaticData)."""
    template = _load_template("rloracle_step_driver_n8n.js")
    return (
        template.replace("__TPL_OBS_NAMES__", json.dumps(observation_names))
        .replace("__TPL_ACT_NAMES__", json.dumps(action_names))
        .replace("__TPL_OBS_PREFIX__", json.dumps(obs_context_prefix))
        .replace("__TPL_STEP_KEY__", json.dumps(step_count_key))
    )


def _render_collector_n8n(
    observation_names: list[str],
    reward_config: dict[str, Any],
    max_steps: int = 600,
    obs_context_prefix: str = "obs_",
    step_count_key: str = "step_count",
) -> str:
    """Render n8n collector template (uses $getWorkflowStaticData)."""
    template = _load_template("rloracle_collector_n8n.js")
    return (
        template.replace("__TPL_OBS_NAMES__", json.dumps(observation_names))
        .replace("__TPL_REWARD__", json.dumps(reward_config or {}))
        .replace("__TPL_MAX_STEPS__", str(max_steps))
        .replace("__TPL_OBS_PREFIX__", json.dumps(obs_context_prefix))
        .replace("__TPL_STEP_KEY__", json.dumps(step_count_key))
    )


def _params_from_adapter_config(adapter_config: dict[str, Any]) -> tuple[list[str], list[str], dict, int]:
    """Extract observation_names, action_names, reward_config, max_steps from adapter_config."""
    io_spec = ExternalIOSpec.from_adapter_config(adapter_config)
    obs_names = [x.name for x in io_spec.observation_spec] if io_spec.obs_dim() > 0 else []
    act_names = [x.name for x in io_spec.action_spec] if io_spec.action_dim() > 0 else []
    reward_config = dict(adapter_config.get("reward_config") or {})
    max_steps = int(adapter_config.get("max_steps", 600))
    return obs_names, act_names, reward_config, max_steps


def _render_step_driver_py(
    action_names: list[str],
    action_key: str = "__rl_oracle_action__",
) -> str:
    """Render PyFlow step driver template (state/inputs)."""
    template = _load_template("rloracle_step_driver.py")
    return (
        template.replace("__TPL_ACT_NAMES__", repr(action_names))
        .replace("__TPL_ACTION_KEY__", repr(action_key))
    )


def _render_collector_py(
    observation_source_ids: list[str],
    reward_config: dict[str, Any],
    max_steps: int = 600,
    step_count_key: str = "step_count",
) -> str:
    """Render PyFlow collector template (state/inputs)."""
    template = _load_template("rloracle_collector.py")
    return (
        template.replace("__TPL_OBS_SOURCE_IDS__", repr(observation_source_ids))
        .replace("__TPL_REWARD__", repr(reward_config or {}))
        .replace("__TPL_MAX_STEPS__", str(max_steps))
        .replace("__TPL_STEP_KEY__", repr(step_count_key))
    )


def _nodes_list(flow: dict | list) -> list[dict[str, Any]]:
    """Return mutable list of node dicts from flow."""
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


def _infer_flow_id(flow: dict | list) -> str:
    """Infer flow/tab id from first node with 'z'."""
    nodes = _nodes_list(flow)
    for n in nodes:
        if isinstance(n, dict) and n.get("z"):
            return str(n["z"])
    return "flow_main"


def inject_oracle_into_flow(
    flow: dict | list,
    adapter_config: dict[str, Any],
    oracle_id: str = "rloracle",
    flow_id: str | None = None,
    step_url: str = "/step",
    *,
    observation_source_ids: list[str] | None = None,
    process_entry_ids: list[str] | None = None,
) -> dict | list:
    """
    Add RLOracle (HTTP In + step driver + collector + HTTP Response) to a Node-RED flow.

    All parameters come from adapter_config: observation_spec, action_spec, reward_config, max_steps.
    No embedded simulations.

    Args:
        flow: Node-RED/EdgeLinkd flow.
        adapter_config: Training config adapter_config (observation_spec, action_spec, reward_config, max_steps).
        oracle_id: Id prefix for Oracle nodes.
        flow_id: Tab id (inferred if None).
        step_url: HTTP path for /step.
        observation_source_ids: Node ids that send observations to the collector (wired from these).
        process_entry_ids: Node ids that receive the step trigger (step driver output 1 wired to these).

    Returns:
        New flow with Oracle nodes added.
    """
    obs_names, act_names, reward_config, max_steps = _params_from_adapter_config(adapter_config)
    if not obs_names:
        obs_names = [f"obs_{i}" for i in range(4)]  # fallback
    if not act_names:
        act_names = [f"act_{i}" for i in range(3)]  # fallback

    nodes = _nodes_list(flow)
    existing_ids = {n.get("id") or n.get("name") for n in nodes if isinstance(n, dict)}
    for suffix in ["", "_step_driver", "_collector", "_http_in", "_http_response"]:
        if oracle_id + suffix in existing_ids:
            raise ValueError(f"Flow already contains node {oracle_id}{suffix}")

    if flow_id is None:
        flow_id = _infer_flow_id(flow)

    step_driver_id = f"{oracle_id}_step_driver"
    collector_id = f"{oracle_id}_collector"
    http_in_id = f"{oracle_id}_http_in"
    http_response_id = f"{oracle_id}_http_response"

    step_count_key = "step_count"
    step_driver_func = _render_step_driver(obs_names, act_names, step_count_key=step_count_key)
    collector_func = _render_collector(
        obs_names, reward_config, max_steps, step_count_key=step_count_key
    )

    collector_wires: list[list[str]] = [[http_response_id]]
    if observation_source_ids:
        for sid in observation_source_ids:
            for n in nodes:
                if isinstance(n, dict) and (n.get("id") or n.get("name")) == sid:
                    wires = list(n.get("wires") or [[]])
                    if not wires:
                        wires = [[]]
                    else:
                        wires = [list(w) for w in wires]
                    if collector_id not in wires[0]:
                        wires[0].append(collector_id)
                    n["wires"] = wires
                    break

    step_driver_wires_out1: list[str] = list(process_entry_ids) if process_entry_ids else []

    http_in_node: dict[str, Any] = {
        "id": http_in_id,
        "type": "http in",
        "z": flow_id,
        "name": f"POST {step_url}",
        "url": step_url,
        "method": "post",
        "upload": False,
        "x": 160,
        "y": 80,
        "wires": [[step_driver_id]],
    }
    step_driver_node: dict[str, Any] = {
        "id": step_driver_id,
        "type": "function",
        "z": flow_id,
        "name": "RLOracle (step)",
        "unitType": "RLOracle",
        "func": step_driver_func,
        "outputs": 2,
        "noerr": 0,
        "x": 400,
        "y": 80,
        "wires": [[http_response_id], [step_driver_wires_out1]],
    }
    collector_node: dict[str, Any] = {
        "id": collector_id,
        "type": "function",
        "z": flow_id,
        "name": "RLOracle (collector)",
        "unitType": "RLOracle",
        "func": collector_func,
        "outputs": 1,
        "noerr": 0,
        "x": 400,
        "y": 140,
        "wires": collector_wires,
    }
    http_response_node: dict[str, Any] = {
        "id": http_response_id,
        "type": "http response",
        "z": flow_id,
        "name": "",
        "statusCode": "",
        "headers": {},
        "x": 620,
        "y": 80,
        "wires": [],
    }

    nodes.extend([http_in_node, step_driver_node, collector_node, http_response_node])
    return _put_back(flow, nodes)


def inject_oracle_into_process_graph(
    graph: ProcessGraph,
    adapter_config: dict[str, Any],
    oracle_id: str = "rloracle",
    *,
    observation_source_ids: list[str] | None = None,
    process_entry_ids: list[str] | None = None,
    language: str = "javascript",
) -> ProcessGraph:
    """
    Add RLOracle unit(s) and code_blocks to ProcessGraph.

    Parameters from adapter_config. No embedded simulations.
    Use language="python" for PyFlow/Ryven; "javascript" for Node-RED/n8n export.

    Returns:
        New ProcessGraph with Oracle units and code_blocks.
    """
    import copy

    graph = copy.deepcopy(graph)
    obs_names, act_names, reward_config, max_steps = _params_from_adapter_config(adapter_config)
    if not obs_names:
        obs_names = [f"obs_{i}" for i in range(4)]
    if not act_names:
        act_names = [f"act_{i}" for i in range(3)]
    obs_source_ids = (
        observation_source_ids
        or adapter_config.get("observation_sources")
        or adapter_config.get("observation_source_ids")
        or []
    )

    step_driver_id = f"{oracle_id}_step_driver"
    collector_id = f"{oracle_id}_collector"
    existing = {u.id for u in graph.units}
    if step_driver_id in existing or collector_id in existing:
        raise ValueError(f"ProcessGraph already contains Oracle unit {oracle_id}")

    if language == "python":
        step_driver_src = _render_step_driver_py(act_names)
        collector_src = _render_collector_py(obs_source_ids, reward_config, max_steps)
        lang = "python"
    else:
        step_driver_src = _render_step_driver(obs_names, act_names)
        collector_src = _render_collector(obs_names, reward_config, max_steps)
        lang = "javascript"

    graph.units.append(
        Unit(
            id=step_driver_id,
            type="RLOracle",
            controllable=False,
            params={"role": "step_driver"},
        )
    )
    graph.units.append(
        Unit(
            id=collector_id,
            type="RLOracle",
            controllable=False,
            params={"role": "collector", "observation_source_ids": obs_source_ids},
        )
    )
    graph.code_blocks.append(
        CodeBlock(id=step_driver_id, language=lang, source=step_driver_src)
    )
    graph.code_blocks.append(
        CodeBlock(id=collector_id, language=lang, source=collector_src)
    )

    for src in observation_source_ids or obs_source_ids or []:
        if graph.get_unit(src):
            graph.connections.append(Connection(from_id=src, to_id=collector_id, from_port="0", to_port="0"))
    for tgt in process_entry_ids or []:
        if graph.get_unit(tgt):
            graph.connections.append(Connection(from_id=step_driver_id, to_id=tgt, from_port="0", to_port="0"))

    return graph


def inject_oracle_into_graph_dict(
    units: list[dict[str, Any]],
    adapter_config: dict[str, Any],
    oracle_id: str,
    *,
    language: str = "javascript",
    observation_source_ids: list[str] | None = None,
    n8n_mode: bool = False,
) -> list[dict[str, Any]]:
    """
    Append RLOracle units (step_driver + collector) to units. Return code_blocks to add.
    Used by apply_graph_edit when add_unit adds type RLOracle.

    Args:
        units: Mutable list of unit dicts (mutated).
        adapter_config: Training adapter_config.
        oracle_id: Id prefix for Oracle units.
        language: "javascript" (Node-RED/n8n) or "python" (PyFlow/Ryven).
        observation_source_ids: Ordered node ids for collector inputs (PyFlow); from adapter_config if omitted.
    """
    obs_names, act_names, reward_config, max_steps = _params_from_adapter_config(adapter_config)
    if not obs_names:
        obs_names = [f"obs_{i}" for i in range(4)]
    if not act_names:
        act_names = [f"act_{i}" for i in range(3)]
    obs_source_ids = observation_source_ids or adapter_config.get("observation_sources") or adapter_config.get("observation_source_ids") or []

    step_driver_id = f"{oracle_id}_step_driver"
    collector_id = f"{oracle_id}_collector"
    existing_ids = {u.get("id") for u in units if isinstance(u, dict)}
    if step_driver_id in existing_ids or collector_id in existing_ids:
        raise ValueError(f"Graph already contains Oracle units for {oracle_id}")

    if language == "python":
        step_driver_src = _render_step_driver_py(act_names)
        collector_src = _render_collector_py(obs_source_ids, reward_config, max_steps)
        lang = "python"
    elif n8n_mode:
        step_driver_src = _render_step_driver_n8n(obs_names, act_names)
        collector_src = _render_collector_n8n(obs_names, reward_config, max_steps)
        lang = "javascript"
    else:
        step_driver_src = _render_step_driver(obs_names, act_names)
        collector_src = _render_collector(obs_names, reward_config, max_steps)
        lang = "javascript"

    units.append({
        "id": step_driver_id,
        "type": "RLOracle",
        "controllable": False,
        "params": {"role": "step_driver"},
    })
    units.append({
        "id": collector_id,
        "type": "RLOracle",
        "controllable": False,
        "params": {"role": "collector", "observation_source_ids": obs_source_ids},
    })
    return [
        {"id": step_driver_id, "language": lang, "source": step_driver_src},
        {"id": collector_id, "language": lang, "source": collector_src},
    ]


def _n8n_connections_ensure(flow: dict) -> dict:
    """Return mutable connections object; create if missing."""
    conns = flow.get("connections")
    if isinstance(conns, dict):
        return conns
    flow["connections"] = {}
    return flow["connections"]


def inject_oracle_into_n8n_flow(
    flow: dict,
    adapter_config: dict[str, Any],
    oracle_id: str = "rloracle",
    step_path: str = "/step",
    *,
    observation_source_ids: list[str] | None = None,
    process_entry_ids: list[str] | None = None,
    position: tuple[float, float] = (240, 200),
) -> dict:
    """
    Add RLOracle (Webhook + step driver Code + Merge + Respond to Webhook + collector Code) to n8n.

    Uses n8n-nodes-base.webhook, n8n-nodes-base.code, n8n-nodes-base.merge,
    n8n-nodes-base.respondToWebhook. All parameters from adapter_config.
    observation_source_ids and process_entry_ids are node **names** (n8n uses names in connections).

    Args:
        flow: n8n workflow dict (nodes + connections).
        adapter_config: Training adapter_config.
        oracle_id: Id/name prefix for Oracle nodes.
        step_path: Webhook path (default /step).
        observation_source_ids: Node names that send observations to collector.
        process_entry_ids: Node names that receive step trigger from step driver output 1.
        position: Base [x, y] for Oracle nodes.

    Returns:
        flow with Oracle nodes added (mutates in place and returns flow).
    """
    obs_names, act_names, reward_config, max_steps = _params_from_adapter_config(adapter_config)
    if not obs_names:
        obs_names = [f"obs_{i}" for i in range(4)]
    if not act_names:
        act_names = [f"act_{i}" for i in range(3)]

    step_driver_name = f"{oracle_id}_step_driver"
    collector_name = f"{oracle_id}_collector"
    webhook_name = f"{oracle_id}_webhook"
    merge_name = f"{oracle_id}_merge"
    respond_name = f"{oracle_id}_respond"

    nodes = flow.get("nodes")
    if not isinstance(nodes, list):
        flow["nodes"] = []
        nodes = flow["nodes"]
    existing = {str(n.get("name") or n.get("id") or "") for n in nodes if isinstance(n, dict)}
    for name in (step_driver_name, collector_name, webhook_name, merge_name, respond_name):
        if name in existing:
            raise ValueError(f"n8n flow already contains node {name}")

    conns = _n8n_connections_ensure(flow)
    step_count_key = "step_count"
    step_driver_code = _render_step_driver_n8n(obs_names, act_names, step_count_key=step_count_key)
    collector_code = _render_collector_n8n(
        obs_names, reward_config, max_steps, step_count_key=step_count_key
    )

    x, y = position
    webhook_node: dict[str, Any] = {
        "id": webhook_name,
        "name": webhook_name,
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [x, y],
        "parameters": {
            "path": step_path,
            "httpMethod": "POST",
            "responseMode": "responseNode",
            "options": {},
        },
        "webhookId": f"{oracle_id}_webhook",
    }
    step_driver_node: dict[str, Any] = {
        "id": step_driver_name,
        "name": step_driver_name,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [x + 220, y],
        "parameters": {"jsCode": step_driver_code},
        "onError": "continue",
    }
    merge_node: dict[str, Any] = {
        "id": merge_name,
        "name": merge_name,
        "type": "n8n-nodes-base.merge",
        "typeVersion": 3,
        "position": [x + 440, y + 80],
        "parameters": {"mode": "append"},
    }
    respond_node: dict[str, Any] = {
        "id": respond_name,
        "name": respond_name,
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1,
        "position": [x + 660, y + 80],
        "parameters": {},
    }
    collector_node: dict[str, Any] = {
        "id": collector_name,
        "name": collector_name,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [x + 440, y + 200],
        "parameters": {"jsCode": collector_code},
        "onError": "continue",
    }

    nodes.extend([webhook_node, step_driver_node, merge_node, respond_node, collector_node])

    # Webhook -> Step Driver
    conns[webhook_name] = {"main": [[{"node": step_driver_name, "type": "main", "index": 0}]]}
    # Step Driver output 0 -> Merge input 1; output 1 -> process entries
    out1_targets = [{"node": merge_name, "type": "main", "index": 0}]
    out2_targets = [{"node": t, "type": "main", "index": 0} for t in (process_entry_ids or [])]
    conns[step_driver_name] = {"main": [out1_targets, out2_targets]}
    # Merge -> Respond to Webhook
    conns[merge_name] = {"main": [[{"node": respond_name, "type": "main", "index": 0}]]}
    # Collector -> Merge input 2
    conns[collector_name] = {"main": [[{"node": merge_name, "type": "main", "index": 1}]]}

    # Wire observation sources -> collector
    for src_name in observation_source_ids or []:
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
        if not any(c.get("node") == collector_name for c in main_out[0]):
            main_out[0].append({"node": collector_name, "type": "main", "index": 0})

    return flow


def _comfyui_ensure_state(workflow: dict[str, Any]) -> dict[str, Any]:
    """Ensure workflow has state with lastNodeId, lastLinkId."""
    state = workflow.get("state")
    if not isinstance(state, dict):
        state = {}
        workflow["state"] = state
    max_node = 0
    for n in workflow.get("nodes") or []:
        if isinstance(n, dict):
            nid = n.get("id")
            if nid is not None:
                try:
                    max_node = max(max_node, int(nid))
                except (ValueError, TypeError):
                    pass
    max_link = 0
    for lnk in workflow.get("links") or []:
        if isinstance(lnk, dict):
            lid = lnk.get("id")
            if lid is not None:
                try:
                    max_link = max(max_link, int(lid))
                except (ValueError, TypeError):
                    pass
    state["lastNodeId"] = max(state.get("lastNodeId", 0), max_node)
    state["lastLinkId"] = max(state.get("lastLinkId", 0), max_link)
    return state


def inject_oracle_into_comfyui_workflow(
    workflow: dict[str, Any],
    adapter_config: dict[str, Any],
    oracle_id: str = "rloracle",
    *,
    observation_source_ids: list[str] | None = None,
    process_entry_ids: list[str] | None = None,
    position: tuple[float, float] = (0, 400),
) -> dict[str, Any]:
    """
    Add RLOracle nodes (RLOracleStepDriver, RLOracleCollector) to a ComfyUI workflow.

    Requires ComfyUI custom nodes RLOracleStepDriver and RLOracleCollector to be installed.
    The bridge (server/comfyui_bridge) exposes /step and drives workflow execution.

    Args:
        workflow: ComfyUI workflow dict (nodes, links, state).
        adapter_config: Training adapter_config (observation_spec, action_spec, reward_config, max_steps).
        oracle_id: Id prefix for Oracle nodes.
        observation_source_ids: Node ids that send observations to collector.
        process_entry_ids: Node ids that receive step trigger (action) from step driver.
        position: Base [x, y] for Oracle nodes.

    Returns:
        workflow with Oracle nodes and links added (mutates in place).
    """
    import json as _json

    obs_names, act_names, reward_config, max_steps = _params_from_adapter_config(adapter_config)
    if not obs_names:
        obs_names = [f"obs_{i}" for i in range(4)]
    if not act_names:
        act_names = [f"act_{i}" for i in range(3)]
    obs_sources = observation_source_ids or adapter_config.get("observation_sources") or adapter_config.get("observation_source_ids") or []
    process_entries = process_entry_ids or []

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
    step_driver_id = f"{oracle_id}_step_driver"
    collector_id = f"{oracle_id}_collector"
    if step_driver_id in node_ids or collector_id in node_ids:
        raise ValueError(f"ComfyUI workflow already contains Oracle nodes for {oracle_id}")

    x, y = position
    step_driver_node_id = next_node_id
    collector_node_id = next_node_id + 1
    next_node_id += 2

    # Links: obs_sources -> collector; step_driver -> process_entries
    collector_input_links: list[int] = []
    for src_id in obs_sources:
        if src_id not in node_ids:
            continue
        lid = next_link_id
        next_link_id += 1
        links.append({
            "id": lid,
            "origin_id": src_id,
            "origin_slot": 0,
            "target_id": collector_node_id,
            "target_slot": len(collector_input_links),
            "type": "FLOAT",
        })
        collector_input_links.append(lid)
        # Add link id to source node's outputs
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
                    else:
                        n["outputs"] = [{"name": "output_0", "type": "FLOAT", "links": out_links}]
                break

    step_driver_output_links: list[int] = []
    for tid in process_entries:
        if tid not in node_ids:
            continue
        lid = next_link_id
        next_link_id += 1
        links.append({
            "id": lid,
            "origin_id": step_driver_node_id,
            "origin_slot": len(step_driver_output_links),
            "target_id": tid,
            "target_slot": 0,
            "type": "FLOAT",
        })
        step_driver_output_links.append(lid)
        # Add input to target node
        for n in nodes:
            if isinstance(n, dict) and str(n.get("id")) == tid:
                ins = n.get("inputs") or []
                ins.append({"name": f"rl_action_{len(ins)}", "type": "FLOAT", "link": lid})
                n["inputs"] = ins
                break

    step_driver_node: dict[str, Any] = {
        "id": step_driver_node_id,
        "type": "RLOracleStepDriver",
        "pos": [x, y],
        "size": [315, 58],
        "flags": {},
        "order": len(nodes),
        "mode": 0,
        "properties": {},
        "inputs": [],
        "outputs": [{"name": "action", "type": "FLOAT", "links": step_driver_output_links}],
        "widgets_values": _json.dumps({"action_names": act_names}),
    }
    collector_node: dict[str, Any] = {
        "id": collector_node_id,
        "type": "RLOracleCollector",
        "pos": [x, y + 120],
        "size": [400, 100],
        "flags": {},
        "order": len(nodes) + 1,
        "mode": 0,
        "properties": {},
        "inputs": [
            {"name": f"obs_{i}", "type": "FLOAT", "link": collector_input_links[i]}
            for i in range(len(collector_input_links))
        ],
        "outputs": [],
        "widgets_values": [_json.dumps(reward_config), max_steps],
    }

    nodes.append(step_driver_node)
    nodes.append(collector_node)
    state["lastNodeId"] = next_node_id - 1
    state["lastLinkId"] = next_link_id - 1

    return workflow
