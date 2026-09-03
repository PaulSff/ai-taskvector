# agents/tools/action_blocks/rename.py

from typing import Literal

from pydantic import field_validator

from agents.tools.types import ActionBlock


class RenameActionBlock(
    ActionBlock[Literal["rename"]]
):
    """Rename a file or folder."""

    path: str
    new_name: str

    @field_validator("path", "new_name")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("value must not be empty")

        return value
