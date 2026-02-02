"""
Env factory: build_env(process_graph, goal, **kwargs) -> gym.Env.
For thermodynamic type: maps canonical graph + goal to TemperatureControlEnv.
"""
from typing import Any

import gymnasium as gym

from schemas.process_graph import ProcessGraph, EnvironmentType
from schemas.training_config import GoalConfig, RewardsConfig

# Lazy import to avoid circular deps and keep temperature_env as optional for other env types
def _get_temperature_env_class():
    from environments.custom.temperature_env import TemperatureControlEnv
    return TemperatureControlEnv


def _validate_thermodynamic_graph(graph: ProcessGraph) -> None:
    """Validate that the process graph has the units needed for thermodynamic temperature mixing."""
    sources = [u for u in graph.units if u.type == "Source"]
    tanks = [u for u in graph.units if u.type == "Tank"]
    valves = [u for u in graph.units if u.type == "Valve" and u.controllable]
    sensors = [u for u in graph.units if u.type == "Sensor"]

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


def _extract_thermodynamic_params(graph: ProcessGraph, goal: GoalConfig) -> dict[str, Any]:
    """Extract TemperatureControlEnv constructor kwargs from canonical process graph + goal."""
    sources = [u for u in graph.units if u.type == "Source"]
    tanks = [u for u in graph.units if u.type == "Tank"]
    # Sort sources by temp: higher = hot, lower = cold
    sources_sorted = sorted(sources, key=lambda u: float(u.params.get("temp", 0)), reverse=True)
    hot_source = sources_sorted[0]
    cold_source = sources_sorted[1]
    tank = tanks[0]

    hot_water_temp = float(hot_source.params.get("temp", 60.0))
    cold_water_temp = float(cold_source.params.get("temp", 10.0))
    max_flow_rate = float(hot_source.params.get("max_flow", 1.0))
    # Use same max_flow for cold if present, else same as hot
    cold_max = cold_source.params.get("max_flow")
    if cold_max is not None:
        max_flow_rate = max(max_flow_rate, float(cold_max))

    capacity = float(tank.params.get("capacity", 1.0))
    cooling_rate = float(tank.params.get("cooling_rate", 0.01))

    target_temp = 37.0
    if goal.target_temp is not None:
        target_temp = float(goal.target_temp)

    return {
        "target_temp": target_temp,
        "initial_temp": 20.0,
        "hot_water_temp": hot_water_temp,
        "cold_water_temp": cold_water_temp,
        "max_flow_rate": max_flow_rate,
        "max_dump_flow_rate": max_flow_rate,
        "mixed_water_cooling_rate": cooling_rate,
        "dt": 0.1,
        "max_steps": 600,
        "render_mode": None,
        "randomize_params": False,
    }


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
        **kwargs: Passed through to env constructor (overrides extracted params).

    Returns:
        gym.Env (e.g. TemperatureControlEnv for thermodynamic).

    Raises:
        ValueError: If environment_type is unsupported or graph is invalid.
    """
    if process_graph.environment_type != EnvironmentType.THERMODYNAMIC:
        raise ValueError(
            f"Unsupported environment_type: {process_graph.environment_type}. "
            "Only thermodynamic is implemented."
        )

    _validate_thermodynamic_graph(process_graph)

    params = _extract_thermodynamic_params(process_graph, goal)
    params["initial_temp"] = initial_temp
    params["max_steps"] = max_steps
    params["randomize_params"] = randomize_params
    params["render_mode"] = render_mode
    params["rewards_config"] = rewards
    params.update(kwargs)

    TemperatureControlEnv = _get_temperature_env_class()
    return TemperatureControlEnv(**params)
