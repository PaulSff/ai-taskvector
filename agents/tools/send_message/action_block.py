
from typing import Literal

from pydantic import field_validator

from agents.tools.types import ActionBlock


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
