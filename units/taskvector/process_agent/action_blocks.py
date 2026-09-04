"""
Parse LLM output into generic action blocks (any dict with an "action" key).

**Content form:** The input is a single string — the raw LLM response. In the agent
workflow this comes from the **LLMAgent** unit (output port `action` → ProcessAgent input
port `action`). The string may be plain text, markdown, and/or contain fenced ```json
blocks or inline { ... } JSON; this module extracts and parses those blocks.

Used by the ProcessAgent unit. Does not reference GraphEditAction or any domain-specific type;
downstream units (e.g. ApplyEdits) filter by their own action set.
Self-contained: JSON block extraction is in this module.

Summary Table

Strategy	Trigger    Main Goal   Key Strength
Fenced  	```json	    Find structured blocks  	Handles nested backticks correctly
Inline  	{ ... }	    Find "naked" JSON	Recovers data when LLM forgets fences
Cleaning	Any block	Fix syntax errors	Allows comments and trailing commas
Filtering	Parsed Obj	Remove noise	Ensures only "Actions" are executed
"""

from __future__ import annotations

from collections.abc import Iterator

from agents.tools.registry import TOOL_ACTION_BLOCKS, parse_action_block
from agents.tools.types import ParsedActions, ParserOutput
from core.schemas.primitives import (
    JsonObject,
    JsonValue,
    is_json_object,
)

from .parser import parse_json_blocks


def parse_action_blocks(content: str) -> ParserOutput:
    """
    Parse LLM content into normalized ParsedActions.
    """
    parsed = parse_json_blocks(content)

    if isinstance(parsed, str):
        return ParserOutput(error=parsed)

    return _parsed_blocks_to_action_blocks(parsed)


def _iter_action_objects(
    parsed_blocks: list[JsonValue],
) -> Iterator[JsonObject]:
    for value in parsed_blocks:
        yield from _iter_action_value(value)


def _iter_action_value(
    value: JsonValue,
) -> Iterator[JsonObject]:
    if isinstance(value, list):
        for item in value:
            yield from _iter_action_value(item)
        return

    if not is_json_object(value):
        return

    action = value.get("action")

    if isinstance(action, str) and action.strip():
        yield value

    for nested in value.values():
        yield from _iter_action_value(nested)


def _parsed_blocks_to_action_blocks(
    parsed_blocks: list[JsonValue],
) -> ParserOutput:
    """
    Convert parsed JSON blocks into a normalized ParsedActions instance.

    ParsedActions is used as the accumulator so the parser does not maintain
    a second, duplicated set of local declarations.
    """

    actions = ParsedActions()

    for raw in _iter_action_objects(parsed_blocks):
        try:
            block = parse_action_block(raw)
        except (TypeError, ValueError):
            continue

        action = raw.get("action")

        if not isinstance(action, str):
            continue

        registration = TOOL_ACTION_BLOCKS.get(action.strip())

        if registration is None or registration.handle is None:
            continue

        registration.handle(actions, block)

    actions.read_file = list(dict.fromkeys(actions.read_file))
    actions.read_code_block_ids = list(
        dict.fromkeys(actions.read_code_block_ids)
    )

    return ParserOutput(actions=actions)


def parse_workflow_edits(content: str) -> ParserOutput:
    """Alias for parse_action_blocks for backward compatibility."""
    return parse_action_blocks(content)
