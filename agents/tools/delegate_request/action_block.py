# agents/tools/action_blocks/delegate_request.py

from typing import Literal

from pydantic import field_validator

from agents.tools.types import ActionBlock


class DelegateRequestActionBlock(
    ActionBlock[Literal["delegate_request"]]
):
    """Delegate the current request to another role."""

    delegate_to: str
    message: str

    @field_validator("delegate_to", "message")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("value must not be empty")

        return value
