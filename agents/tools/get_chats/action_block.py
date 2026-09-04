from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from agents.tools.registry import register_action_block
from agents.tools.types import ActionBlock, ParsedActions


class GetUnreadActionBlock(
    ActionBlock[Literal["get_unread"]]
):
    """Fetch unread incoming messages from a supported messenger."""

    messenger: str

    @field_validator("messenger")
    @classmethod
    def validate_messenger(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("messenger must not be empty")

        return value


def handle_get_unread(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, GetUnreadActionBlock):
        raise TypeError(
            "Expected a get_unread action block, "
            f"got {type(block).__name__}"
        )

    actions.add_tool_action(
        "get_unread",
        block.as_json_object(),
    )


def register_get_unread_action_blocks() -> None:
    register_action_block(
        "get_unread",
        GetUnreadActionBlock,
        handler=handle_get_unread,
    )
