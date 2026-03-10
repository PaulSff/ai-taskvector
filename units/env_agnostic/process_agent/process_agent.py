"""
ProcessAgent (Parser) unit: parses LLM response into structured edits.

Input: action (raw response string from LLMAgent).
Output: edits (list of edit dicts or dict with edits, request_file_content, etc.).
Used in the assistant workflow flow: LLMAgent -> ProcessAgent -> ApplyEdits.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

from assistants.process_assistant import parse_workflow_edits

PROCESS_AGENT_INPUT_PORTS = [("action", "Any")]
PROCESS_AGENT_OUTPUT_PORTS = [("edits", "Any")]


def _process_agent_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parse LLM response to edits (list or dict with edits + side channels)."""
    raw = inputs.get("action")
    if raw is None:
        out: Any = []
    elif isinstance(raw, str):
        out = parse_workflow_edits(raw)
    else:
        out = parse_workflow_edits(str(raw))
    return ({"edits": out}, state)


def register_process_agent() -> None:
    """Register the ProcessAgent unit type."""
    register_unit(UnitSpec(
        type_name="ProcessAgent",
        input_ports=PROCESS_AGENT_INPUT_PORTS,
        output_ports=PROCESS_AGENT_OUTPUT_PORTS,
        step_fn=_process_agent_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Parses LLM response (action) into structured edits for ApplyEdits.",
    ))


__all__ = ["register_process_agent", "PROCESS_AGENT_INPUT_PORTS", "PROCESS_AGENT_OUTPUT_PORTS"]
