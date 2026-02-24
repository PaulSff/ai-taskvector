"""
Training Assistant backend: merge config edit → normalizer → canonical TrainingConfig.
Reward shaping uses direct DSL actions (reward_formula_add, reward_formula_set, etc.).
"""
from typing import Any

from normalizer import to_training_config
from schemas.training_config import TrainingConfig


def training_config_summary(current: TrainingConfig | dict[str, Any] | None) -> dict[str, Any]:
    """Reduce training config to a small, LLM-friendly summary."""
    if current is None:
        return {}
    cfg = current.model_dump() if isinstance(current, TrainingConfig) else dict(current)
    goal = cfg.get("goal") or {}
    rewards = cfg.get("rewards") or {}
    algo = cfg.get("algorithm")
    hyper = cfg.get("hyperparameters") or {}
    return {
        "algorithm": algo,
        "goal": {k: goal.get(k) for k in ("type", "target_temp", "target_volume_ratio", "target_pressure_range") if k in goal},
        "rewards": {
            "preset": rewards.get("preset"),
            "formula": rewards.get("formula"),
            "weights": rewards.get("weights"),
            "rules": rewards.get("rules"),
        },
        "hyperparameters": {k: hyper.get(k) for k in ("learning_rate", "n_steps", "batch_size", "n_epochs") if k in hyper},
    }


from assistants.config_edits import apply_config_edit


def training_assistant_apply(
    current: TrainingConfig | dict[str, Any],
    edit: dict[str, Any],
) -> TrainingConfig:
    """
    Merge assistant config edit into current config and return canonical TrainingConfig.
    current: existing TrainingConfig or raw dict (e.g. from YAML).
    edit: partial config from RL Coach (goal, rewards, hyperparameters, etc.).
        Reward edits use direct DSL actions: reward_formula_add, reward_formula_set, etc.
    """
    if isinstance(current, TrainingConfig):
        raw = current.model_dump()
    else:
        raw = dict(current)
    merged = apply_config_edit(raw, edit)
    return to_training_config(merged, format="dict")
