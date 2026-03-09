"""
Web env loader: build from process_graph + goal via env_factory.
Python-only (browser, web_search units). No Node-RED/PyFlow export.
"""
from pathlib import Path
from typing import Any

import gymnasium as gym

from env_factory import build_env
from normalizer import load_process_graph_from_file
from schemas.process_graph import ProcessGraph
from schemas.training_config import GoalConfig, RewardsConfig


def load_web_env(
    config: dict[str, Any],
    *,
    process_graph: ProcessGraph | None = None,
    goal: GoalConfig | None = None,
    **kwargs: Any,
) -> gym.Env:
    """
    Build web env from process graph + goal (delegate to env_factory).
    Config may include: process_graph_path, goal, rewards.
    """
    if process_graph is None:
        path = config.get("process_graph_path")
        if not path:
            raise ValueError("Web config must include 'process_graph_path' or pass process_graph")
        process_graph = load_process_graph_from_file(Path(path))

    if goal is None:
        goal_raw = config.get("goal")
        if goal_raw is None:
            goal = GoalConfig()
        else:
            goal = GoalConfig.model_validate(goal_raw) if isinstance(goal_raw, dict) else goal_raw

    rewards_raw = config.get("rewards")
    if isinstance(rewards_raw, dict):
        from schemas.training_config import RewardsConfig
        rewards = RewardsConfig.model_validate(rewards_raw)
    else:
        rewards = None

    return build_env(
        process_graph,
        goal,
        rewards=rewards,
        **kwargs,
    )
