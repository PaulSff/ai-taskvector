from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from agents.tools.get_chats import run_get_chats_follow_up
from agents.tools.registry import register_tool
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


def register_get_unread_tool() -> None:
    register_tool(
        "get_unread",
        run_get_chats_follow_up,
        action_blocks={
            "get_unread": GetUnreadActionBlock,
        },
        action_handlers={
            "get_unread": handle_get_unread,
        },
    )


register_get_unread_tool()
