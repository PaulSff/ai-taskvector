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


def _params_from_adapter_config(adapter_config: dict[str, Any]) -> tuple[list[str], list[str], dict, int]:
    """Extract observation_names, action_names, reward_config, max_steps from adapter_config."""
    io_spec = ExternalIOSpec.from_adapter_config(adapter_config)
    obs_names = [x.name for x in io_spec.observation_spec] if io_spec.obs_dim() > 0 else []
    act_names = [x.name for x in io_spec.action_spec] if io_spec.action_dim() > 0 else []
    reward_config = dict(adapter_config.get("reward_config") or {})
    max_steps = int(adapter_config.get("max_steps", 600))
    return obs_names, act_names, reward_config, max_steps


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
) -> ProcessGraph:
    """
    Add RLOracle unit(s) and code_blocks to ProcessGraph.

    Parameters from adapter_config. No embedded simulations.

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

    step_driver_id = f"{oracle_id}_step_driver"
    collector_id = f"{oracle_id}_collector"
    existing = {u.id for u in graph.units}
    if step_driver_id in existing or collector_id in existing:
        raise ValueError(f"ProcessGraph already contains Oracle unit {oracle_id}")

    step_driver_src = _render_step_driver(obs_names, act_names)
    collector_src = _render_collector(obs_names, reward_config, max_steps)

    graph.units.append(
        Unit(
            id=step_driver_id,
            type="RLOracle",
            controllable=False,
            params={"role": "step_driver", "code_block_id": f"{step_driver_id}_code"},
        )
    )
    graph.units.append(
        Unit(
            id=collector_id,
            type="RLOracle",
            controllable=False,
            params={"role": "collector", "code_block_id": f"{collector_id}_code"},
        )
    )
    graph.code_blocks.append(
        CodeBlock(id=f"{step_driver_id}_code", language="javascript", source=step_driver_src)
    )
    graph.code_blocks.append(
        CodeBlock(id=f"{collector_id}_code", language="javascript", source=collector_src)
    )

    for src in observation_source_ids or []:
        if graph.get_unit(src):
            graph.connections.append(Connection(from_id=src, to_id=collector_id))
    for tgt in process_entry_ids or []:
        if graph.get_unit(tgt):
            graph.connections.append(Connection(from_id=step_driver_id, to_id=tgt))

    return graph


def inject_oracle_into_graph_dict(
    units: list[dict[str, Any]],
    adapter_config: dict[str, Any],
    oracle_id: str,
) -> list[dict[str, Any]]:
    """
    Append RLOracle units (step_driver + collector) to units. Return code_blocks to add.
    Used by apply_graph_edit when add_unit adds type RLOracle.
    """
    obs_names, act_names, reward_config, max_steps = _params_from_adapter_config(adapter_config)
    if not obs_names:
        obs_names = [f"obs_{i}" for i in range(4)]
    if not act_names:
        act_names = [f"act_{i}" for i in range(3)]

    step_driver_id = f"{oracle_id}_step_driver"
    collector_id = f"{oracle_id}_collector"
    existing_ids = {u.get("id") for u in units if isinstance(u, dict)}
    if step_driver_id in existing_ids or collector_id in existing_ids:
        raise ValueError(f"Graph already contains Oracle units for {oracle_id}")

    step_driver_src = _render_step_driver(obs_names, act_names)
    collector_src = _render_collector(obs_names, reward_config, max_steps)

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
        "params": {"role": "collector"},
    })
    return [
        {"id": step_driver_id, "language": "javascript", "source": step_driver_src},
        {"id": collector_id, "language": "javascript", "source": collector_src},
    ]
