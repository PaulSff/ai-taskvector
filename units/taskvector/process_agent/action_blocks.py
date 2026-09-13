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

import logging
from collections.abc import Iterator

from agents.tools.registry import (
    get_action_registration,
    parse_action_block,
)
from agents.tools.types import ParsedActions, ParserOutput
from core.schemas.primitives import (
    JsonObject,
    JsonValue,
    is_json_object,
)
from services.logging import setup_colored_logging

from .parser import parse_json_blocks

logger = setup_colored_logging(logging.DEBUG)
# logger = logging.getLogger(__name__)


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
    actions = ParsedActions()

    for raw in _iter_action_objects(parsed_blocks):
        action = raw.get("action")

        logger.debug("Discovered action block: action=%r raw=%r", action, raw)

        try:
            block = parse_action_block(raw)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Rejected action block: action=%r error=%s raw=%r",
                action,
                exc,
                raw,
            )
            continue

        if not isinstance(action, str):
            logger.warning("Skipping action with non-string name: raw=%r", raw)
            continue

        registration = get_action_registration(action)

        if registration is None:
            logger.warning(
                "No registration found for action=%r raw=%r",
                action,
                raw,
            )
            continue

        if registration.handle is None:
            logger.warning(
                "Action has no handler: action=%r raw=%r",
                action,
                raw,
            )
            continue

        logger.info("Dispatching a tool call: action=%r raw=%r", action, raw)

        registration.handle(actions, block)

    return ParserOutput(actions=actions)


def parse_workflow_edits(content: str) -> ParserOutput:
    """Alias for parse_action_blocks for backward compatibility."""
    return parse_action_blocks(content)
