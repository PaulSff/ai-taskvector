"""
Training Assistant backend: merge config edit → normalizer → canonical TrainingConfig.
"""
from typing import Any

from normalizer import to_training_config
from schemas.training_config import TrainingConfig

from assistants.config_edits import apply_config_edit


def training_assistant_apply(
    current: TrainingConfig | dict[str, Any],
    edit: dict[str, Any],
) -> TrainingConfig:
    """
    Merge assistant config edit into current config and return canonical TrainingConfig.
    current: existing TrainingConfig or raw dict (e.g. from YAML).
    edit: partial config from Training Assistant (goal, rewards, hyperparameters, etc.).
    """
    if isinstance(current, TrainingConfig):
        raw = current.model_dump()
    else:
        raw = dict(current)
    merged = apply_config_edit(raw, edit)
    return to_training_config(merged, format="dict")
