"""
Custom thermodynamic env: build from process_graph + goal via env_factory.
"""
from pathlib import Path
from typing import Any

import gymnasium as gym
from env_factory import build_env
from normalizer import load_process_graph_from_file
from schemas.process_graph import ProcessGraph
from schemas.training_config import GoalConfig


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

    return build_env(process_graph, goal, **kwargs)
