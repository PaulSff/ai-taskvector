"""
ProcessAgent (Parser) unit: parses LLM response into generic action blocks.

Uses the same JSON-block syntax for any domain (graph edits, config, etc.). Output is a list
of action dicts (each has "action": str + payload) or a dict with "edits" and optional side
channels. Downstream units decide which actions they consume (e.g. ApplyEdits uses only
GraphEditAction; other units can consume different action types from the same stream).
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

from .action_blocks import parse_action_blocks

PROCESS_AGENT_INPUT_PORTS = [("action", "Any")]
PROCESS_AGENT_OUTPUT_PORTS = [("edits", "Any"), ("error", "str")]


def _process_agent_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parse LLM response to generic action blocks (list or dict with edits + side channels)."""
    raw = inputs.get("action")
    if raw is None:
        out: Any = []
        err: str | None = None
    elif isinstance(raw, str):
        out = parse_action_blocks(raw)
        err = out.get("parse_error") if isinstance(out, dict) else None
    else:
        out = parse_action_blocks(str(raw))
        err = out.get("parse_error") if isinstance(out, dict) else None
    return ({"edits": out, "error": err}, state)


def register_process_agent() -> None:
    """Register the ProcessAgent unit type."""
    register_unit(UnitSpec(
        type_name="ProcessAgent",
        input_ports=PROCESS_AGENT_INPUT_PORTS,
        output_ports=PROCESS_AGENT_OUTPUT_PORTS,
        step_fn=_process_agent_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Parses LLM response into generic action blocks; downstream units filter by action type.",
    ))


__all__ = ["register_process_agent", "PROCESS_AGENT_INPUT_PORTS", "PROCESS_AGENT_OUTPUT_PORTS"]
