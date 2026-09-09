from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from agents.tools.registry import register_tool
from agents.tools.send_message import run_send_message_follow_up
from agents.tools.types import ActionBlock, ParsedActions


class SendMessageActionBlock(
    ActionBlock[Literal["send_message"]]
):
    """Send a message to a chat over a supported messenger."""

    messenger: str
    chat_id: str
    message: str

    @field_validator("messenger", "chat_id", "message")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("value must not be empty")

        return value


def handle_send_message(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, SendMessageActionBlock):
        raise TypeError(
            "Expected a send_message action block, "
            f"got {type(block).__name__}"
        )

    actions.add_tool_action(
        "send_message",
        block.as_json_object(),
    )


def register_send_message_tool() -> None:
    register_tool(
        "send_message",
        run_send_message_follow_up,
        action_blocks={
            "send_message": SendMessageActionBlock,
        },
        action_handlers={
            "send_message": handle_send_message,
        },
    )


register_send_message_tool()
