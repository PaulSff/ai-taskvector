from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from agents.tools.registry import register_action_block
from agents.tools.types import ActionBlock, ParsedActions


class NoActionBlock(
    ActionBlock[Literal["no_action"]]
):
    """Indicate that no tool action should be taken."""

    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("reason must not be empty")

        return value


def handle_no_action(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, NoActionBlock):
        raise TypeError(
            "Expected a no_action action block, "
            f"got {type(block).__name__}"
        )

    actions.add_tool_action(
        "no_action",
        block.as_json_object(),
    )


def register_no_action_action_blocks() -> None:
    register_action_block(
        "no_action",
        NoActionBlock,
        handler=handle_no_action,
    )
