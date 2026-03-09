"""
Data/BI env loader: build from process_graph + goal via env_factory.
"""
from pathlib import Path
from typing import Any

import gymnasium as gym

from core.env_factory import build_env
from core.normalizer import load_process_graph_from_file
from core.schemas.process_graph import ProcessGraph
from core.schemas.training_config import GoalConfig, RewardsConfig


def load_data_bi_env(
    config: dict[str, Any],
    *,
    process_graph: ProcessGraph | None = None,
    goal: GoalConfig | None = None,
    **kwargs: Any,
) -> gym.Env:
    """
    Build data_bi env from process graph + goal (delegate to env_factory).
    Config may include: process_graph_path, goal, rewards, data_path, user_metadata_path.
    """
    if process_graph is None:
        path = config.get("process_graph_path")
        if not path:
            raise ValueError(
                "Data_BI config must include 'process_graph_path' or pass process_graph"
            )
        process_graph = load_process_graph_from_file(Path(path))

    if goal is None:
        goal_raw = config.get("goal")
        if goal_raw is None:
            raise ValueError("Data_BI config must include 'goal' or pass goal")
        goal = GoalConfig.model_validate(goal_raw) if isinstance(goal_raw, dict) else goal_raw

    rewards_raw = config.get("rewards")
    if isinstance(rewards_raw, dict):
        rewards = RewardsConfig.model_validate(rewards_raw)
    elif isinstance(rewards_raw, RewardsConfig):
        rewards = rewards_raw
    else:
        rewards = None

    return build_env(
        process_graph,
        goal,
        rewards=rewards,
        data_path=config.get("data_path"),
        **kwargs,
    )
