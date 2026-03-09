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

from core.schemas.training_config import TrainingConfig


_TEXT_TO_REWARD_SYSTEM = """You are a reward-shaping assistant for reinforcement learning. The user describes how they want the agent to be rewarded or penalized. You output ONLY a JSON object with a "rewards" key. Prefer formula (DSL) over weights. No explanation, no markdown, no code block—just the raw JSON.

## Reward schema
- formula: list of { "expr": "DSL expression", "weight": float } or { "expr": "condition", "reward": float }
  - expr uses get(outputs, "unit_id.port", default), goal.get("target_temp", 37), goal.get("target_volume_ratio"), observation[i]
  - Common unit_ids: mixer_tank (temp, volume_ratio, volume), hot_valve/cold_valve/dump_valve (flow)
  - weight: numeric term, contribution = weight * eval(expr). Example: -abs(get(outputs, 'mixer_tank.temp', 0) - goal.get('target_temp', 37))
  - reward: conditional bonus when expr is truthy. Example: "get(outputs, 'mixer_tank.volume_ratio', 0) >= 0.8 and get(outputs, 'mixer_tank.volume_ratio', 0) <= 0.85"
- rules: list of { "condition": "expression", "reward_delta": float }. Condition uses get(outputs, "unit_id.port", 0), goal, etc.

## Examples
User: "Penalize dumping more"
Output: {"rewards": {"formula": [{"expr": "get(outputs, 'dump_valve.flow', 0)", "weight": -0.2}]}}

User: "Reward being close to target temperature"
Output: {"rewards": {"formula": [{"expr": "abs(get(outputs, 'mixer_tank.temp', 0) - goal.get('target_temp', 37)) < 1.0", "reward": 10.0}]}}

User: "If temperature error is above 10, add a big penalty"
Output: {"rewards": {"rules": [{"condition": "abs(get(outputs, 'mixer_tank.temp', 0) - goal.get('target_temp', 37)) > 10", "reward_delta": -5.0}]}}

User: "Stronger penalty for dumping when volume is high"
Output: {"rewards": {"rules": [{"condition": "get(outputs, 'dump_valve.flow', 0) > 0 and get(outputs, 'mixer_tank.volume_ratio', 0) > 0.85", "reward_delta": -2.0}]}}

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


def _resolve_ollama_model(model: str | None) -> str:
    """Resolve model from settings when not provided (assistants use settings only)."""
    if model and str(model).strip():
        return str(model).strip()
    try:
        from gui.flet.components.settings import get_llm_provider_config, DEFAULT_OLLAMA_MODEL
        cfg = get_llm_provider_config(assistant="rl_coach")
        return (cfg.get("model") or DEFAULT_OLLAMA_MODEL).strip()
    except ImportError:
        return "llama3.2"


def text_to_reward(
    text: str,
    current_config: TrainingConfig | dict[str, Any] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """
    Turn natural-language reward description into a reward config edit using Ollama.

    Args:
        text: User description (e.g. "Penalize dumping more and reward temperature range").
        current_config: Optional current TrainingConfig or dict; if provided, current rewards
            are included in the prompt so the model can refine rather than replace.
        model: Ollama model name (default from settings when available).

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

    resolved_model = _resolve_ollama_model(model)
    response = ollama.chat(
        model=resolved_model,
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
    model: str | None = None,
) -> TrainingConfig:
    """
    Convenience: text → reward edit → merge into current config → return canonical TrainingConfig.
    """
    from assistants.training_assistant import training_assistant_apply

    edit = text_to_reward(text, current_config=current, model=model)
    return training_assistant_apply(current, edit)
