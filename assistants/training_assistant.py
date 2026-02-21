"""
Training Assistant backend: merge config edit → normalizer → canonical TrainingConfig.
When the RL Coach outputs reward_from_text, reward shaping is delegated to text-to-reward.
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
            "weights": rewards.get("weights"),
            "rules": rewards.get("rules"),
        },
        "hyperparameters": {k: hyper.get(k) for k in ("learning_rate", "n_steps", "batch_size", "n_epochs") if k in hyper},
    }


from assistants.config_edits import apply_config_edit


def training_assistant_apply(
    current: TrainingConfig | dict[str, Any],
    edit: dict[str, Any],
    *,
    reward_model: str = "llama3.2",
) -> TrainingConfig:
    """
    Merge assistant config edit into current config and return canonical TrainingConfig.
    current: existing TrainingConfig or raw dict (e.g. from YAML).
    edit: partial config from RL Coach (goal, rewards, hyperparameters, etc.).
        If edit["action"] == "reward_from_text", the reward_description is passed to
        text_to_reward and the resulting reward edit is merged (RL Coach uses text-to-reward for reward shaping).
    reward_model: Ollama model used when resolving reward_from_text (default llama3.2).
    """
    if isinstance(current, TrainingConfig):
        raw = current.model_dump()
    else:
        raw = dict(current)

    if edit.get("action") == "reward_from_text":
        from assistants.text_to_reward import text_to_reward

        description = edit.get("reward_description", "").strip()
        if not description:
            return to_training_config(raw, format="dict")
        reward_edit = text_to_reward(
            description,
            current_config=current,
            model=edit.get("model") or reward_model,
        )
        merged = apply_config_edit(raw, reward_edit)
    else:
        merged = apply_config_edit(raw, edit)

    return to_training_config(merged, format="dict")
