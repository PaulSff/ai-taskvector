"""
Apply a single training-config edit (merge + normalize), parallel to ``apply_edit_via_workflow`` for graphs.

Re-exported from ``assistants`` for library callers (same merge semantics as ``ApplyTrainingConfigEdits`` / ``run_apply_training_config_edits``).
Merge semantics live in ``core.gym.training_edits``; RL Coach workflows use the ApplyTrainingConfigEdits unit instead.
"""
from __future__ import annotations

from typing import Any

from core.gym.training_edits import apply_config_edit
from core.normalizer import to_training_config
from core.schemas.training_config import TrainingConfig


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


def apply_training_config_edit(
    current: TrainingConfig | dict[str, Any],
    edit: dict[str, Any],
) -> TrainingConfig:
    """
    Merge one assistant config edit into the current config and return canonical TrainingConfig.

    ``current``: existing TrainingConfig or raw dict (e.g. from YAML).
    ``edit``: partial config from RL Coach (goal, rewards, hyperparameters, etc.) or reward DSL actions
    ``reward_formula_add``, ``reward_formula_set``, ``reward_rules_add``, ``reward_rules_set``.
    """
    if isinstance(current, TrainingConfig):
        raw = current.model_dump()
    else:
        raw = dict(current)
    merged = apply_config_edit(raw, edit)
    return to_training_config(merged, format="dict")


__all__ = ["apply_training_config_edit", "training_config_summary"]
