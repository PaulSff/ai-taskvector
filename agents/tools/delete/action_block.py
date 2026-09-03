from typing import Literal

from pydantic import field_validator

from agents.tools.types import ActionBlock


class DeleteActionBlock(
    ActionBlock[Literal["delete"]]
):
    """Delete a file or folder."""

    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("path must not be empty")

        return value
