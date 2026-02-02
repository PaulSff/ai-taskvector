"""
Text-to-reward: natural language → reward config edit via Ollama.

User describes the reward goal in text (e.g. "Penalize dumping more and reward
being in temperature range"); Ollama returns structured reward edit (weights, rules)
as JSON; we merge into TrainingConfig. See docs/REWARD_RULES.md.

Requires: pip install ollama, Ollama running with a model (e.g. ollama pull llama3.2).
"""
import json
import re
from typing import Any

from schemas.training_config import TrainingConfig


_TEXT_TO_REWARD_SYSTEM = """You are a reward-shaping assistant for reinforcement learning. The user describes how they want the agent to be rewarded or penalized. You output ONLY a JSON object with a "rewards" key: preset (optional), weights (optional), and/or rules (optional). No explanation, no markdown, no code block—just the raw JSON.

## Reward schema
- preset: one of temperature_and_volume, pressure_control, goal_reaching, exploration
- weights: dict of component name → float (negative = penalty, positive = bonus). Components: temp_error, volume_in_range, dumping, step_penalty
- rules: list of { "condition": "expression", "reward_delta": float }. Condition is a Python-like expression over state (e.g. "temp_error > 5", "volume < 0.8"). reward_delta is added when condition is true.

## Examples
User: "Penalize dumping more"
Output: {"rewards": {"weights": {"dumping": -0.2}}}

User: "Reward being close to target temperature"
Output: {"rewards": {"weights": {"temp_error": -0.5, "volume_in_range": 10.0}}}

User: "If temperature error is above 10, add a big penalty"
Output: {"rewards": {"rules": [{"condition": "temp_error > 10", "reward_delta": -5.0}]}}

User: "Stronger penalty for dumping when volume is high"
Output: {"rewards": {"rules": [{"condition": "dump_flow > 0 and volume > 0.85", "reward_delta": -2.0}]}}

Output ONLY valid JSON. No other text."""


def _parse_reward_edit(content: str) -> dict[str, Any]:
    """Extract JSON from LLM response. Prefer ```json ... ``` block; else try full string."""
    content = content.strip()
    # Try ```json ... ``` block first
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if match:
        raw = match.group(1).strip()
    else:
        raw = content
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to find first { ... } in content
        start = content.find("{")
        if start != -1:
            depth = 0
            end = start
            for i, c in enumerate(content[start:], start):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if depth == 0:
                data = json.loads(content[start : end + 1])
            else:
                raise ValueError("Could not parse JSON from response")
        else:
            raise ValueError("No JSON object found in response")
    if "rewards" not in data:
        data = {"rewards": data}
    return data


def text_to_reward(
    text: str,
    current_config: TrainingConfig | dict[str, Any] | None = None,
    model: str = "llama3.2",
) -> dict[str, Any]:
    """
    Turn natural-language reward description into a reward config edit using Ollama.

    Args:
        text: User description (e.g. "Penalize dumping more and reward temperature range").
        current_config: Optional current TrainingConfig or dict; if provided, current rewards
            are included in the prompt so the model can refine rather than replace.
        model: Ollama model name (e.g. llama3.2, mistral, qwen2.5).

    Returns:
        Edit dict suitable for training_assistant_apply: {"rewards": {"preset": ..., "weights": {...}, "rules": [...]}}.
        Merge with current config and pass to training_assistant_apply(current, edit).

    Raises:
        ImportError: If ollama is not installed (pip install ollama).
        ValueError: If Ollama response could not be parsed as JSON.
    """
    try:
        import ollama
    except ImportError:
        raise ImportError(
            "text_to_reward requires ollama. Install with: pip install ollama. "
            "Then start Ollama and pull a model: ollama pull llama3.2"
        )

    user_msg = text.strip()
    if not user_msg:
        return {"rewards": {}}

    if current_config is not None:
        if isinstance(current_config, TrainingConfig):
            rewards = current_config.rewards.model_dump()
        else:
            rewards = (current_config.get("rewards") or {})
        if isinstance(rewards, dict):
            current_rewards_str = json.dumps(rewards, indent=2)
        else:
            current_rewards_str = str(rewards)
        user_msg = f"Current rewards config:\n{current_rewards_str}\n\nUser request: {user_msg}\n\nOutput only the JSON edit for rewards (and optionally preset/weights/rules)."
    else:
        user_msg = f"User request: {user_msg}\n\nOutput only the JSON edit."

    messages = [
        {"role": "system", "content": _TEXT_TO_REWARD_SYSTEM},
        {"role": "user", "content": user_msg},
    ]

    response = ollama.chat(
        model=model,
        messages=messages,
        options={"temperature": 0.3, "num_predict": 512},
    )
    content = response.get("message", {}).get("content", "")
    if not content:
        return {"rewards": {}}

    return _parse_reward_edit(content)


def text_to_reward_apply(
    text: str,
    current: TrainingConfig | dict[str, Any],
    model: str = "llama3.2",
) -> TrainingConfig:
    """
    Convenience: text → reward edit → merge into current config → return canonical TrainingConfig.
    """
    from assistants.training_assistant import training_assistant_apply

    edit = text_to_reward(text, current_config=current, model=model)
    return training_assistant_apply(current, edit)
