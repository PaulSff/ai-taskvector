"""
Config edit merge for Training Assistant.
Partial config edits are deep-merged into current config; then normalizer.to_training_config(merged) yields canonical TrainingConfig.
"""
from typing import Any


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Deep-merge override into base. override wins for leaf values.
    Lists are replaced (not merged). Used for training config edits.
    """
    result = dict(base)
    for key, value in override.items():
        if key not in result:
            result[key] = value
        elif isinstance(value, dict) and isinstance(result[key], dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def apply_config_edit(current: dict[str, Any], edit: dict[str, Any]) -> dict[str, Any]:
    """
    Merge edit (partial training config) into current config.
    If edit contains {"action": "no_edit", "reason": "..."}, returns current unchanged.
    Otherwise deep_merge(current, edit). Result is suitable for normalizer.to_training_config(merged, format="dict").
    """
    if edit.get("action") == "no_edit":
        return dict(current)
    return deep_merge(current, edit)
