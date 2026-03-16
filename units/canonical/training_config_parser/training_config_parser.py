"""
TrainingConfigParser unit: parses LLM response into a list of training-config edit blocks.

Used by the RL Coach workflow. Same JSON-block extraction as ProcessAgent (fenced ```json
and inline {...}), but every parsed dict is treated as one edit (no_edit, partial config
like goal/hyperparameters, or reward_formula_add etc.). Downstream ApplyTrainingConfigEdits
applies them via core.gym.training_edits.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

from units.canonical.process_agent.action_blocks import _parse_json_blocks

TRAINING_CONFIG_PARSER_INPUT_PORTS = [("action", "Any")]
TRAINING_CONFIG_PARSER_OUTPUT_PORTS = [("edits", "Any"), ("error", "str")]


def _training_config_parser_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parse LLM response to list of edit dicts (training config only)."""
    raw = inputs.get("action")
    if raw is None:
        return ({"edits": [], "error": None}, state)
    content = str(raw).strip()
    parsed = _parse_json_blocks(content)
    if isinstance(parsed, dict) and "parse_error" in parsed:
        return ({"edits": [], "error": parsed.get("parse_error", "Parse error")}, state)
    if not isinstance(parsed, list):
        return ({"edits": [], "error": None}, state)
    edits = [x for x in parsed if isinstance(x, dict)]
    return ({"edits": edits, "error": None}, state)


def register_training_config_parser() -> None:
    """Register the TrainingConfigParser unit type."""
    register_unit(UnitSpec(
        type_name="TrainingConfigParser",
        input_ports=TRAINING_CONFIG_PARSER_INPUT_PORTS,
        output_ports=TRAINING_CONFIG_PARSER_OUTPUT_PORTS,
        step_fn=_training_config_parser_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Parses LLM response into training-config edit blocks (no_edit, goal, rewards, reward_formula_add, etc.).",
    ))


__all__ = [
    "register_training_config_parser",
    "TRAINING_CONFIG_PARSER_INPUT_PORTS",
    "TRAINING_CONFIG_PARSER_OUTPUT_PORTS",
]
