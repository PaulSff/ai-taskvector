"""
Custom thermodynamic env: build from process_graph + goal via env_factory.
"""
from pathlib import Path
from typing import Any

import gymnasium as gym
from env_factory import build_env
from normalizer import load_process_graph_from_file
from schemas.process_graph import ProcessGraph
from schemas.training_config import GoalConfig, RewardsConfig

# Default process graph path (same topology as legacy temperature env)
_DEFAULT_PROCESS_GRAPH = Path(__file__).resolve().parents[2] / "config" / "examples" / "temperature_process.yaml"


def build_chat_env(
    *,
    target_temp: float = 37.0,
    initial_temp: float = 20.0,
    hot_water_temp: float = 60.0,
    cold_water_temp: float = 10.0,
    max_flow_rate: float = 1.0,
    max_steps: int = 600,
    render_mode: str | None = None,
    process_graph_path: Path | str | None = None,
) -> gym.Env:
    """
    Build thermodynamic env from chat-style parameters (for chat_with_model, chat_with_ai, etc.).
    Uses default process graph and overrides unit params as needed.
    """
    path = Path(process_graph_path) if process_graph_path else _DEFAULT_PROCESS_GRAPH
    graph = load_process_graph_from_file(path)
    # Override source temps and max_flow (hot = higher temp, cold = lower)
    sources = sorted(
        [u for u in graph.units if u.type == "Source"],
        key=lambda x: float(x.params.get("temp", 0)),
        reverse=True,
    )
    if len(sources) >= 2:
        sources[0].params = {**sources[0].params, "temp": hot_water_temp, "max_flow": max_flow_rate}
        sources[1].params = {**sources[1].params, "temp": cold_water_temp, "max_flow": max_flow_rate}
    goal = GoalConfig(target_temp=target_temp)
    return load_thermodynamic_env(
        {},
        process_graph=graph,
        goal=goal,
        initial_temp=initial_temp,
        max_steps=max_steps,
        render_mode=render_mode,
    )


def load_thermodynamic_env(
    config: dict[str, Any],
    *,
    process_graph: ProcessGraph | None = None,
    goal: GoalConfig | None = None,
    **kwargs: Any,
) -> gym.Env:
    """
    Build thermodynamic env from process graph + goal (delegate to env_factory).

    Config may include:
      process_graph_path: path to process graph YAML/JSON
      goal: goal dict (target_temp, target_volume_ratio, etc.)
      rewards: optional rewards config (preset, weights, rules)
    If process_graph or goal are passed directly, they override config.
    """
    if process_graph is None:
        path = config.get("process_graph_path")
        if not path:
            raise ValueError("Custom thermodynamic config must include 'process_graph_path' or pass process_graph")
        process_graph = load_process_graph_from_file(Path(path))

    if goal is None:
        goal_raw = config.get("goal")
        if goal_raw is None:
            raise ValueError("Custom thermodynamic config must include 'goal' or pass goal")
        goal = GoalConfig.model_validate(goal_raw) if isinstance(goal_raw, dict) else goal_raw

    rewards_raw = config.get("rewards")
    if isinstance(rewards_raw, dict):
        rewards = RewardsConfig.model_validate(rewards_raw)
    elif isinstance(rewards_raw, RewardsConfig):
        rewards = rewards_raw
    else:
        rewards = None

    return build_env(process_graph, goal, rewards=rewards, **kwargs)
