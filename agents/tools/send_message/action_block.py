from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from agents.tools.registry import register_action_block
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


def register_send_message_action_blocks() -> None:
    register_action_block(
        "send_message",
        SendMessageActionBlock,
        handler=handle_send_message,
    )
