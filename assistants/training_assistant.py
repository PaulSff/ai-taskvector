"""
Training Assistant backend: merge config edit → normalizer → canonical TrainingConfig.
When the RL Coach outputs reward_from_text, reward shaping is delegated to text-to-reward.
"""
from typing import Any

from normalizer import to_training_config
from schemas.training_config import TrainingConfig

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
