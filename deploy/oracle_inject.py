"""
Inject RLOracle (step handler) into Node-RED flows and ProcessGraph.

Uses template-based Oracle implementations per runtime. Templates are in deploy/templates/.
See docs/DEPLOYMENT_NODERED.md.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from schemas.process_graph import CodeBlock, Connection, ProcessGraph, Unit

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _load_template(name: str) -> str:
    """Load template source by name (e.g. rloracle_node_red_thermodynamic.js)."""
    path = _TEMPLATES_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Oracle template not found: {path}")
    return path.read_text()


def _render_thermodynamic_oracle(
    *,
    observation_names: list[str] | None = None,
    action_names: list[str] | None = None,
    target_temp: float = 37,
    initial_temp: float = 20,
    hot_water_temp: float = 60,
    cold_water_temp: float = 10,
    max_steps: int = 600,
    tank_capacity: float = 1,
    ambient_temp: float = 20,
    dt: float = 0.1,
    temp_min: float = 0,
    temp_max: float = 100,
    mixed_water_cooling_rate: float = 0.01,
) -> str:
    """Render the thermodynamic mixing-tank Oracle template with given params."""
    observation_names = observation_names or ["thermometer_cold", "thermometer_hot", "thermometer_tank", "water_level"]
    action_names = action_names or ["cold_valve", "dump_valve", "hot_valve"]
    params = {
        "target_temp": target_temp,
        "initial_temp": initial_temp,
        "hot_water_temp": hot_water_temp,
        "cold_water_temp": cold_water_temp,
        "max_flow_rate": 1,
        "max_dump_flow_rate": 1,
        "mixed_water_cooling_rate": mixed_water_cooling_rate,
        "dt": dt,
        "max_steps": max_steps,
        "tank_capacity": tank_capacity,
        "ambient_temp": ambient_temp,
        "temp_min": temp_min,
        "temp_max": temp_max,
    }
    template = _load_template("rloracle_node_red_thermodynamic.js")
    source = template.replace("{{PARAMS}}", json.dumps(params))
    source = source.replace("{{OBSERVATION_NAMES}}", json.dumps(observation_names))
    source = source.replace("{{ACTION_NAMES}}", json.dumps(action_names))
    return source


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


def _infer_flow_id(flow: dict | list) -> str:
    """Infer the flow/tab id (z) from the first node that has one, or default."""
    nodes = _nodes_list(flow)
    for n in nodes:
        if isinstance(n, dict) and n.get("z"):
            return str(n["z"])
    return "flow_main"


def inject_oracle_into_flow(
    flow: dict | list,
    oracle_id: str = "rloracle",
    flow_id: str | None = None,
    *,
    template: str = "thermodynamic",
    observation_names: list[str] | None = None,
    action_names: list[str] | None = None,
    step_url: str = "/step",
    **kwargs: Any,
) -> dict | list:
    """
    Add RLOracle (HTTP In + Function + HTTP Response) to a Node-RED/EdgeLinkd flow.

    For thermodynamic template, kwargs can include: target_temp, initial_temp, hot_water_temp,
    cold_water_temp, max_steps, tank_capacity, ambient_temp, dt, temp_min, temp_max,
    mixed_water_cooling_rate.

    Args:
        flow: Node-RED/EdgeLinkd flow (list of nodes or { nodes } / { flows }).
        oracle_id: Id for the Oracle function node.
        flow_id: Tab/flow id to attach nodes to (used as 'z' in Node-RED).
        template: Template name ('thermodynamic' for mixing tank).
        observation_names: Ordered observation vector names.
        action_names: Ordered action vector names.
        step_url: HTTP path for /step (default /step).
        **kwargs: Template-specific params (target_temp, etc.).

    Returns:
        New flow with Oracle nodes added.
    """
    nodes = _nodes_list(flow)
    existing_ids = {n.get("id") or n.get("name") for n in nodes if isinstance(n, dict)}
    if oracle_id in existing_ids:
        raise ValueError(f"Flow already contains a node with id {oracle_id}")

    if flow_id is None:
        flow_id = _infer_flow_id(flow)

    http_in_id = f"{oracle_id}_http_in"
    http_response_id = f"{oracle_id}_http_response"
    if http_in_id in existing_ids or http_response_id in existing_ids:
        raise ValueError(f"Flow already contains Oracle HTTP nodes ({http_in_id}, {http_response_id})")

    if template == "thermodynamic":
        func_source = _render_thermodynamic_oracle(
            observation_names=observation_names,
            action_names=action_names,
            **{k: v for k, v in kwargs.items() if k in (
                "target_temp", "initial_temp", "hot_water_temp", "cold_water_temp",
                "max_steps", "tank_capacity", "ambient_temp", "dt", "temp_min", "temp_max",
                "mixed_water_cooling_rate",
            )},
        )
    else:
        raise ValueError(f"Unknown Oracle template: {template}")

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
        "wires": [[oracle_id]],
    }
    oracle_node: dict[str, Any] = {
        "id": oracle_id,
        "type": "function",
        "z": flow_id,
        "name": "RLOracle",
        "unitType": "RLOracle",
        "func": func_source,
        "outputs": 2,
        "noerr": 0,
        "x": 400,
        "y": 80,
        "wires": [[http_response_id], []],
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

    nodes.extend([http_in_node, oracle_node, http_response_node])
    return _put_back(flow, nodes)


def inject_oracle_into_process_graph(
    graph: ProcessGraph,
    oracle_id: str = "rloracle",
    *,
    template: str = "thermodynamic",
    observation_source_ids: list[str] | None = None,
    action_target_ids: list[str] | None = None,
    observation_names: list[str] | None = None,
    action_names: list[str] | None = None,
    **kwargs: Any,
) -> ProcessGraph:
    """
    Add RLOracle unit and code_block to a ProcessGraph.

    The Oracle unit is added; observation/action names come from spec or from
    observation_source_ids/action_target_ids if names not provided. The code_block
    is rendered from the template and stored for roundtrip/export.

    Args:
        graph: ProcessGraph to mutate (or a copy is returned).
        oracle_id: Unit id for the Oracle.
        template: Template name ('thermodynamic').
        observation_source_ids: Unit ids that provide observations (for naming fallback).
        action_target_ids: Unit ids that receive actions (for naming fallback).
        observation_names: Explicit observation vector names.
        action_names: Explicit action vector names.
        **kwargs: Template params (target_temp, etc.).

    Returns:
        New ProcessGraph with Oracle unit and code_block added.
    """
    import copy
    graph = copy.deepcopy(graph)
    existing_ids = {u.id for u in graph.units}
    if oracle_id in existing_ids:
        raise ValueError(f"ProcessGraph already contains unit {oracle_id}")

    obs_names = observation_names or observation_source_ids or ["thermometer_cold", "thermometer_hot", "thermometer_tank", "water_level"]
    act_names = action_names or action_target_ids or ["cold_valve", "dump_valve", "hot_valve"]

    if template == "thermodynamic":
        source = _render_thermodynamic_oracle(
            observation_names=obs_names if isinstance(obs_names, list) else list(obs_names),
            action_names=act_names if isinstance(act_names, list) else list(act_names),
            **{k: v for k, v in kwargs.items() if k in (
                "target_temp", "initial_temp", "hot_water_temp", "cold_water_temp",
                "max_steps", "tank_capacity", "ambient_temp", "dt", "temp_min", "temp_max",
                "mixed_water_cooling_rate",
            )},
        )
    else:
        raise ValueError(f"Unknown Oracle template: {template}")

    code_block_id = f"{oracle_id}_code"
    unit = Unit(
        id=oracle_id,
        type="RLOracle",
        controllable=False,
        params={"code_block_id": code_block_id, "template": template},
    )
    code_block = CodeBlock(
        id=code_block_id,
        language="javascript",
        source=source,
    )

    graph.units.append(unit)
    graph.code_blocks.append(code_block)

    if observation_source_ids:
        for src in observation_source_ids:
            if graph.get_unit(src):
                graph.connections.append(Connection(from_id=src, to_id=oracle_id))
    if action_target_ids:
        for tgt in action_target_ids:
            if graph.get_unit(tgt):
                graph.connections.append(Connection(from_id=oracle_id, to_id=tgt))

    return graph
