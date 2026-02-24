"""
Env factory: build_env(process_graph, goal, **kwargs) -> gym.Env.

For thermodynamic type: uses GraphEnv (graph-based) with unit registry
(Source, Valve, Tank, Sensor). No fallback.
"""
from typing import Any

import gymnasium as gym

from schemas.process_graph import ProcessGraph, EnvironmentType
from schemas.training_config import GoalConfig, RewardsConfig


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
    # Sensor optional but typical
    if len(sensors) < 1:
        pass  # optional

    if len(agents) != 1:
        raise ValueError(
            f"Process graph must contain exactly one RLAgent unit (wired before training); got {len(agents)}"
        )
    agent_id = agents[0].id
    into_agent = [c for c in graph.connections if c.to_id == agent_id]
    from_agent = [c for c in graph.connections if c.from_id == agent_id]
    if not into_agent:
        raise ValueError(
            f"RLAgent node '{agent_id}' must have inputs (observations) wired: at least one connection into the agent"
        )
    if not from_agent:
        raise ValueError(
            f"RLAgent node '{agent_id}' must have outputs (actions) wired: at least one connection from the agent"
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
    if process_graph.environment_type != EnvironmentType.THERMODYNAMIC:
        raise ValueError(
            f"Unsupported environment_type: {process_graph.environment_type}. "
            "Only thermodynamic is implemented."
        )

    _validate_thermodynamic_graph(process_graph)
    from environments.graph_env import GraphEnv
    from environments.custom.thermodynamics import ThermodynamicEnvSpec

    spec = ThermodynamicEnvSpec(initial_temp=initial_temp, initial_volume_ratio=kwargs.get("initial_volume_ratio"))
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
