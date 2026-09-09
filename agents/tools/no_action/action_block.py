from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from agents.tools.no_action import run_no_action_follow_up
from agents.tools.registry import register_tool
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


def register_no_action_tool() -> None:
    register_tool(
        "no_action",
        run_no_action_follow_up,
        action_blocks={
            "no_action": NoActionBlock,
        },
        action_handlers={
            "no_action": handle_no_action,
        },
    )


register_no_action_tool()
