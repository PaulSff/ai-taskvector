"""
Data normalizer: map raw input (dict, YAML, Node-RED) to canonical ProcessGraph and TrainingConfig.
All external formats flow through here so the rest of the stack sees one schema.
"""
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import ValidationError

from schemas.process_graph import CodeBlock, EnvironmentType, ProcessGraph, Unit, Connection
from schemas.training_config import (
    TrainingConfig,
    GoalConfig,
    RewardsConfig,
    HyperparametersConfig,
    CallbacksConfig,
    RunConfig,
)

FormatProcess = Literal["yaml", "dict", "node_red", "template"]
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
    Map Node-RED flow JSON to canonical process graph dict (environment_type, units, connections).
    Convention: nodes with type in (Source, Valve, Tank, Sensor) or unitType set are process units.
    id = node.id; type = node.unitType or node.type; params = node.params or {}; wires → connections.

    Standard Node-RED nodes (function, inject, exec, mqtt in, http request, debug, etc.) are
    ignored: only process-unit types above are included. Connections are kept only between
    process units; wires to/from other nodes are dropped.
    """
    nodes = _node_red_nodes_list(raw)
    env_type = "thermodynamic"
    if isinstance(raw, dict):
        env_type = str(raw.get("environment_type", raw.get("process_environment_type", env_type)))

    unit_ids: set[str] = set()
    units: list[dict[str, Any]] = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("id") or n.get("name")
        if nid is None:
            continue
        nid = str(nid)
        # Unit type: explicit unitType/processType, or node.type if it's a process unit type
        ntype = n.get("unitType") or n.get("processType") or n.get("type")
        if ntype is None:
            continue
        ntype = str(ntype)
        if ntype not in PROCESS_UNIT_TYPES:
            continue
        unit_ids.add(nid)
        params = dict(n.get("params") or n.get("payload") or {})
        controllable = n.get("controllable")
        if controllable is None:
            controllable = ntype == "Valve"
        else:
            controllable = bool(controllable)
        units.append({"id": nid, "type": ntype, "controllable": controllable, "params": params})

    connections: list[dict[str, str]] = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        from_id = n.get("id") or n.get("name")
        if from_id is None:
            continue
        from_id = str(from_id)
        if from_id not in unit_ids:
            continue
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

    return {
        "environment_type": env_type,
        "units": units,
        "connections": connections,
    }


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


def to_process_graph(raw: dict[str, Any] | str | list[Any], format: FormatProcess = "dict") -> ProcessGraph:
    """
    Normalize raw input to canonical ProcessGraph.
    Use everywhere process data is loaded so consistency is guaranteed.

    Args:
        raw: Dict (canonical shape), YAML string, or Node-RED flow (dict/list/JSON str).
        format: "dict" | "yaml" | "node_red".

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
    else:
        raise ValueError(
            "format must be 'dict', 'yaml', 'node_red', or 'template'"
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

    return ProcessGraph(
        environment_type=env_type,
        units=units,
        connections=connections,
        code_blocks=code_blocks,
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

    return TrainingConfig(
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
    format: None = infer from suffix (.yaml/.yml → yaml, .json → node_red), or explicit 'yaml'|'dict'|'node_red'.
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
