"""
ProcessAgent (Parser) unit: parses LLM response into generic action blocks.

Uses the same JSON-block syntax for any domain (graph edits, tool calls).

parse raw LLM output
        ↓
normalize into ParserOutput
        ├── actions: ParsedActions
        │   ├── edits: list[GraphEdit]
        │   └── tool_actions: dict[str, list[Data]]
        └── error
        ↓
workflow response
        ↓
downstream consumers
"""
from agents.tools.types import ParserOutput
from core.schemas.primitives import Data, Output
from units.registry import UnitSpec, register_unit

from .action_blocks import parse_action_blocks

PROCESS_AGENT_INPUT_PORTS = [("message", "Any")]
PROCESS_AGENT_OUTPUT_PORTS = [
    ("actions", "ParsedActions"),
    ("error", "str"),
]


def _process_agent_step(
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
) -> Output:
    """Parse LLM response into nested actions and an optional error."""

    raw = inputs.get("message")

    if raw is None:
        result = ParserOutput()
    elif isinstance(raw, str):
        result = parse_action_blocks(raw)
    else:
        result = parse_action_blocks(str(raw))

    return (
        {
            "actions": result.actions,
            "error": result.error,
        },
        state,
    )

def register_process_agent() -> None:
    """Register the ProcessAgent unit type."""
    register_unit(UnitSpec(
        type_name="ProcessAgent",
        input_ports=PROCESS_AGENT_INPUT_PORTS,
        output_ports=PROCESS_AGENT_OUTPUT_PORTS,
        step_fn=_process_agent_step,
        environment_tags=["taskvector"],
        environment_tags_are_agnostic=False,
        description="Parses LLM response into generic action blocks; downstream units filter by action type.",
    ))


__all__ = ["PROCESS_AGENT_INPUT_PORTS", "PROCESS_AGENT_OUTPUT_PORTS", "register_process_agent"]
