"""
RAG native env loader: build GraphEnv from process graph + goal via env_factory.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import gymnasium as gym

from core.env_factory import build_env
from core.normalizer import load_process_graph_from_file
from core.schemas.process_graph import ProcessGraph
from core.schemas.training_config import GoalConfig, RewardsConfig


def load_rag_env(
    config: dict[str, Any],
    *,
    process_graph: ProcessGraph | None = None,
    goal: GoalConfig | None = None,
    **kwargs: Any,
) -> gym.Env:
    """
    Build a ``rag`` primary-environment Gym env from process graph + goal.

    Config may include: ``process_graph_path``, ``goal``, ``rewards`` (same shape as data_bi / web loaders).
    """
    if process_graph is None:
        path = config.get("process_graph_path")
        if not path:
            raise ValueError("rag config must include 'process_graph_path' or pass process_graph")
        process_graph = load_process_graph_from_file(Path(path))

    if goal is None:
        goal_raw = config.get("goal")
        if goal_raw is None:
            raise ValueError("rag config must include 'goal' or pass goal")
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
        **kwargs,
    )
