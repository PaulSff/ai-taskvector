from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from agents.tools.registry import register_action_block
from agents.tools.types import ActionBlock, ParsedActions


class GrepActionBlock(
    ActionBlock[Literal["grep"]]
):
    """Search for a pattern inside a file."""

    pattern: str
    source: str

    @field_validator("pattern", "source")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("value must not be empty")

        return value


def handle_grep(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, GrepActionBlock):
        raise TypeError(
            "Expected a grep action block, "
            f"got {type(block).__name__}"
        )

    actions.add_tool_action(
        "grep",
        block.as_json_object(),
    )


def register_grep_action_blocks() -> None:
    register_action_block(
        "grep",
        GrepActionBlock,
        handler=handle_grep,
    )
