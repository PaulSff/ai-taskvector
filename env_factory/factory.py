"""
Env factory: build_env(process_graph, goal, **kwargs) -> gym.Env.

For thermodynamic type: uses GraphEnv (graph-based) with unit registry.
Requires canonical topology (units with roles step_driver, join, switch). If the
graph has an RLAgent/LLMAgent with obs/action wiring but no canonical units, they are injected.
"""
from typing import Any

import gymnasium as gym

from schemas.process_graph import Connection, EnvironmentType, PortSpec, ProcessGraph, Unit
from schemas.training_config import GoalConfig, RewardsConfig

from schemas.agent_node import (
    get_agent_observation_input_ids,
    get_agent_action_output_ids,
    get_policy_node,
    has_canonical_topology,
)
from units.registry import get_unit_spec, get_type_by_role

_CANONICAL_JOIN_ID = "collector"
_CANONICAL_SWITCH_ID = "switch"
_CANONICAL_STEP_DRIVER_ID = "step_driver"
_CANONICAL_SPLIT_ID = "split"
_START_PORT_BY_TYPE: dict[str, str] = {"Source": "0", "Tank": "5"}


def _enrich_unit_ports_from_registry(unit: Unit) -> Unit:
    """Fill unit input_ports/output_ports from registry if missing."""
    spec = get_unit_spec(unit.type)
    if spec is None:
        return unit
    in_ports = list(unit.input_ports) if unit.input_ports else [PortSpec(name=n, type=t or None) for n, t in spec.input_ports]
    out_ports = list(unit.output_ports) if unit.output_ports else [PortSpec(name=n, type=t or None) for n, t in spec.output_ports]
    if in_ports == unit.input_ports and out_ports == unit.output_ports:
        return unit
    return unit.model_copy(update={"input_ports": in_ports, "output_ports": out_ports})


def _inject_canonical_topology(graph: ProcessGraph) -> ProcessGraph:
    """If graph has a policy node with obs/action wiring but no canonical units (by role), add them and rewire."""
    if has_canonical_topology(graph):
        return graph
    policy = get_policy_node(graph)
    if policy is None:
        return graph
    obs_ids = get_agent_observation_input_ids(graph)
    act_ids = get_agent_action_output_ids(graph)
    if not obs_ids or not act_ids:
        return graph

    type_join = get_type_by_role("join")
    type_switch = get_type_by_role("switch")
    type_step_driver = get_type_by_role("step_driver")
    type_split = get_type_by_role("split")
    if not type_join or not type_switch or not type_step_driver:
        return graph  # registry not loaded or roles missing; validation will fail

    unit_ids = {u.id for u in graph.units}
    unit_by_id = {u.id: u for u in graph.units}
    new_units: list[Unit] = [_enrich_unit_ports_from_registry(u) for u in graph.units]
    new_connections: list[Connection] = list(graph.connections)

    def add_unit(uid: str, utype: str, params: dict[str, Any]) -> None:
        spec = get_unit_spec(utype)
        if spec is None:
            return
        new_units.append(Unit(
            id=uid,
            type=utype,
            controllable=False,
            params=params,
            input_ports=[PortSpec(name=n, type=t or None) for n, t in spec.input_ports],
            output_ports=[PortSpec(name=n, type=t or None) for n, t in spec.output_ports],
        ))

    if _CANONICAL_JOIN_ID not in unit_ids:
        add_unit(_CANONICAL_JOIN_ID, type_join, {"num_inputs": max(len(obs_ids), 1)})
        for i, sid in enumerate(sorted(obs_ids)):
            if sid in unit_ids:
                new_connections.append(Connection(from_id=sid, to_id=_CANONICAL_JOIN_ID, from_port="0", to_port=str(i)))

    if _CANONICAL_SWITCH_ID not in unit_ids:
        add_unit(_CANONICAL_SWITCH_ID, type_switch, {"num_outputs": max(len(act_ids), 1)})
        for i, tid in enumerate(sorted(act_ids)):
            if tid in unit_ids:
                new_connections.append(Connection(from_id=_CANONICAL_SWITCH_ID, to_id=tid, from_port=str(i), to_port="0"))

    if _CANONICAL_STEP_DRIVER_ID not in unit_ids:
        add_unit(_CANONICAL_STEP_DRIVER_ID, type_step_driver, {})

    simulator_ids = [u.id for u in graph.units if u.type in ("Source", "Tank")]
    if _CANONICAL_SPLIT_ID not in unit_ids and simulator_ids and type_split:
        add_unit(_CANONICAL_SPLIT_ID, type_split, {"num_outputs": max(len(simulator_ids), 1)})
        new_connections.append(Connection(from_id=_CANONICAL_STEP_DRIVER_ID, to_id=_CANONICAL_SPLIT_ID, from_port="0", to_port="0"))
        for i, sim_id in enumerate(sorted(simulator_ids)):
            u = unit_by_id.get(sim_id)
            to_port = _START_PORT_BY_TYPE.get((u.type if u else ""), "0")
            new_connections.append(Connection(from_id=_CANONICAL_SPLIT_ID, to_id=sim_id, from_port=str(i), to_port=to_port))

    return graph.model_copy(update={"units": new_units, "connections": new_connections})


def _validate_thermodynamic_graph(graph: ProcessGraph) -> None:
    """Validate that the process graph has the units needed for thermodynamic temperature mixing."""
    sources = [u for u in graph.units if u.type == "Source"]
    tanks = [u for u in graph.units if u.type == "Tank"]
    valves = [u for u in graph.units if u.type == "Valve" and u.controllable]
    sensors = [u for u in graph.units if u.type == "Sensor"]
    agents = [u for u in graph.units if u.type == "RLAgent"]

    if len(sources) < 2:
        raise ValueError(
            f"Thermodynamic env requires at least 2 Source units (hot/cold); got {len(sources)}"
        )
    if len(tanks) < 1:
        raise ValueError("Thermodynamic env requires at least 1 Tank unit; got 0")
    if len(valves) < 3:
        raise ValueError(
            f"Thermodynamic env requires 3 controllable Valve units (hot, cold, dump); got {len(valves)}"
        )
    if len(sensors) < 1:
        pass  # optional

    if not has_canonical_topology(graph):
        raise ValueError(
            "Thermodynamic graph must have canonical topology (units with roles step_driver, join, switch). "
            "Add an RLAgent or LLMAgent with observation_source_ids and action_target_ids to auto-create them."
        )


def _validate_data_bi_graph(graph: ProcessGraph) -> None:
    """Validate process graph for data_bi: at least one DataSource, one RLAgent."""
    from schemas.agent_node import get_agent_observation_input_ids, get_agent_action_output_ids

    sources = [u for u in graph.units if u.type == "DataSource"]
    agents = [u for u in graph.units if u.type == "RLAgent"]
    if len(sources) < 1:
        raise ValueError("Data_BI env requires at least 1 DataSource unit")
    if len(agents) != 1:
        raise ValueError(
            f"Process graph must contain exactly one RLAgent unit; got {len(agents)}"
        )
    agent_id = agents[0].id
    into_agent = [c for c in graph.connections if c.to_id == agent_id]
    from_agent = [c for c in graph.connections if c.from_id == agent_id]
    if not into_agent:
        raise ValueError(
            f"RLAgent '{agent_id}' must have inputs (observations) wired"
        )
    if not from_agent:
        raise ValueError(
            f"RLAgent '{agent_id}' must have outputs (actions) wired"
        )


def build_env(
    process_graph: ProcessGraph,
    goal: GoalConfig,
    *,
    rewards: RewardsConfig | None = None,
    initial_temp: float = 20.0,
    max_steps: int = 600,
    randomize_params: bool = False,
    render_mode: str | None = None,
    **kwargs: Any,
) -> gym.Env:
    """
    Build a Gymnasium env from canonical process graph and goal config.

    Args:
        process_graph: Canonical process graph (from normalizer).
        goal: Canonical goal config (from normalizer or TrainingConfig.goal).
        rewards: Optional rewards config (preset, weights, rules); rules evaluated at step time.
        initial_temp: Initial tank temperature (for thermodynamic).
        max_steps: Max steps per episode.
        randomize_params: Whether to randomize physics params on reset (for training).
        render_mode: Gymnasium render mode (e.g. "human").
        **kwargs: Passed through to GraphEnv constructor.

    Returns:
        gym.Env (GraphEnv for thermodynamic).

    Raises:
        ValueError: If environment_type is unsupported or graph is invalid.
    """
    if process_graph.environment_type == EnvironmentType.THERMODYNAMIC:
        from units.thermodynamic import register_thermodynamic_units
        from units.canonical import register_canonical_units
        register_thermodynamic_units()
        register_canonical_units()  # needed for _inject_canonical_topology (Join, Switch, StepDriver, Split)
        process_graph = _inject_canonical_topology(process_graph)
        _validate_thermodynamic_graph(process_graph)
        from environments.native.thermodynamics import ThermodynamicEnvSpec
        from environments.graph_env import GraphEnv

        spec = ThermodynamicEnvSpec(
            initial_temp=initial_temp,
            initial_volume_ratio=kwargs.get("initial_volume_ratio"),
        )
        return GraphEnv(
            process_graph,
            goal,
            spec,
            dt=kwargs.get("dt", 0.1),
            max_steps=max_steps,
            rewards_config=rewards,
            render_mode=render_mode,
            randomize_params=randomize_params,
            initial_temp=initial_temp,
            initial_volume_ratio=kwargs.get("initial_volume_ratio"),
            **kwargs,
        )

    if process_graph.environment_type == EnvironmentType.DATA_BI:
        _validate_data_bi_graph(process_graph)
        from environments.native.data_bi import DataBIEnvSpec
        from environments.graph_env import GraphEnv

        spec = DataBIEnvSpec(data_path=kwargs.get("data_path"))
        return GraphEnv(
            process_graph,
            goal,
            spec,
            dt=kwargs.get("dt", 0.1),
            max_steps=max_steps,
            rewards_config=rewards,
            render_mode=render_mode,
            randomize_params=randomize_params,
            **kwargs,
        )

    if process_graph.environment_type == EnvironmentType.WEB:
        from environments.native.web import WebEnvSpec
        from environments.graph_env import GraphEnv

        spec = WebEnvSpec()
        return GraphEnv(
            process_graph,
            goal,
            spec,
            dt=kwargs.get("dt", 0.1),
            max_steps=max_steps,
            rewards_config=rewards,
            render_mode=render_mode,
            randomize_params=randomize_params,
            **kwargs,
        )

    raise ValueError(
        f"Unsupported environment_type: {process_graph.environment_type}. "
        "Supported: thermodynamic, data_bi, web."
    )
