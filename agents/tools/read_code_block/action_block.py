
from typing import Literal

from pydantic import field_validator

from agents.tools.types import ActionBlock


class ReadCodeBlockActionBlock(
    ActionBlock[Literal["read_code_block"]]
):
    """Request the source code for a code block from the graph."""

    id: str

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("id must not be empty")

        return value
