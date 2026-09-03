
from typing import Literal

from pydantic import field_validator

from agents.tools.types import ActionBlock


class GrepActionBlock(
    ActionBlock[Literal["grep"]]
):
    """Search for a pattern inside a file."""

    pattern: str
    source: str

    @field_validator("pattern", "source")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("value must not be empty")

        return value
