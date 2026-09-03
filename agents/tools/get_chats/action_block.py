
from typing import Literal

from pydantic import field_validator

from agents.tools.types import ActionBlock


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
