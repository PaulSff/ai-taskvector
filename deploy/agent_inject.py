"""
Template-based RLAgent injection for Node-RED.

Adds prepare (Function) + http request + parse (Function) nodes that call an
inference service. Universal API: POST /predict {observation} -> {action}.
Similar to Oracle: template-based, works with any trained model.
Run the inference server: python -m deploy.rl_inference_server --model path/to/model.zip
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from schemas.external_io_spec import ExternalIOSpec

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _load_template(name: str) -> str:
    path = _TEMPLATES_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Agent template not found: {path}")
    return path.read_text()


def _render_prepare(
    observation_names: list[str],
    inference_url: str,
    obs_prefix: str = "rl_obs_",
) -> str:
    template = _load_template("rl_agent_prepare.js")
    return (
        template.replace("__TPL_OBS_NAMES__", json.dumps(observation_names))
        .replace("__TPL_OBS_PREFIX__", json.dumps(obs_prefix))
        .replace("__TPL_INFERENCE_URL__", json.dumps(inference_url))
    )


def _observation_names_from_config(adapter_config: dict[str, Any]) -> list[str]:
    io_spec = ExternalIOSpec.from_adapter_config(adapter_config)
    return [x.name for x in io_spec.observation_spec] if io_spec.obs_dim() > 0 else []


def _nodes_list(flow: dict | list) -> list[dict[str, Any]]:
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
    nodes = _nodes_list(flow)
    for n in nodes:
        if isinstance(n, dict) and n.get("z"):
            return str(n["z"])
    return "flow_main"


def inject_agent_template_into_flow(
    flow: dict | list,
    agent_id: str,
    model_path: str,
    observation_source_ids: list[str],
    action_target_ids: list[str],
    *,
    adapter_config: dict[str, Any] | None = None,
    inference_url: str = "http://127.0.0.1:8000/predict",
    flow_id: str | None = None,
) -> dict | list:
    """
    Add template-based RLAgent nodes (prepare + http request + parse) to Node-RED flow.

    Observation sources must send msg.topic = observation_name (per adapter_config).
    The inference service must be running: python -m deploy.rl_inference_server --model <path>.

    Args:
        flow: Node-RED/EdgeLinkd flow.
        agent_id: Unique id for the agent subflow (prefix for node ids).
        model_path: Path to trained model (for docs; server loads it).
        observation_source_ids: Node ids that send observations (wired to prepare).
        action_target_ids: Node ids that receive actions (parse output wired to these).
        adapter_config: Training adapter_config for observation_names; else inferred from ids.
        inference_url: URL of the inference server (default http://127.0.0.1:8000/predict).
        flow_id: Tab id (inferred if None).

    Returns:
        New flow with RLAgent template nodes added.
    """
    cfg = adapter_config or {}
    obs_names = _observation_names_from_config(cfg)
    if not obs_names:
        obs_names = [f"obs_{i}" for i in range(len(observation_source_ids))]

    prepare_id = f"{agent_id}_prepare"
    http_id = f"{agent_id}_http"
    parse_id = f"{agent_id}_parse"

    nodes = _nodes_list(flow)
    existing = {n.get("id") or n.get("name") for n in nodes if isinstance(n, dict)}
    for nid in (prepare_id, http_id, parse_id):
        if nid in existing:
            raise ValueError(f"Flow already contains node {nid}")

    if flow_id is None:
        flow_id = _infer_flow_id(flow)

    prepare_func = _render_prepare(obs_names, inference_url)

    prepare_node: dict[str, Any] = {
        "id": prepare_id,
        "type": "function",
        "z": flow_id,
        "name": f"RLAgent prepare",
        "func": prepare_func,
        "outputs": 1,
        "noerr": 0,
        "x": 400,
        "y": 120,
        "wires": [[http_id]],
    }
    http_node: dict[str, Any] = {
        "id": http_id,
        "type": "http request",
        "z": flow_id,
        "name": "predict",
        "method": "POST",
        "paytoqs": "ignore",
        "url": inference_url,
        "tls": "",
        "persist": False,
        "proxy": "",
        "authType": "",
        "sendsPayload": True,
        "x": 620,
        "y": 120,
        "wires": [[parse_id]],
    }
    parse_func = _load_template("rl_agent_parse.js")
    parse_node: dict[str, Any] = {
        "id": parse_id,
        "type": "function",
        "z": flow_id,
        "name": "RLAgent parse",
        "unitType": "RLAgent",
        "func": parse_func,
        "outputs": 1,
        "noerr": 0,
        "x": 840,
        "y": 120,
        "wires": [list(action_target_ids)],
    }

    for sid in observation_source_ids:
        for n in nodes:
            if isinstance(n, dict) and (n.get("id") or n.get("name")) == sid:
                wires = list(n.get("wires") or [])
                if not wires:
                    wires = [[]]
                else:
                    wires = [list(w) for w in wires]
                if prepare_id not in wires[0]:
                    wires[0].append(prepare_id)
                n["wires"] = wires
                break

    nodes.extend([prepare_node, http_node, parse_node])
    return _put_back(flow, nodes)
