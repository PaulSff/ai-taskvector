
from typing import Literal

from pydantic import field_validator

from agents.tools.types import ActionBlock


class WebSearchActionBlock(
    ActionBlock[Literal["web_search"]]
):
    """Search the web with DuckDuckGo."""

    query: str
    max_results: str

    @field_validator("query", "max_results")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("value must not be empty")

        return value

    @field_validator("max_results")
    @classmethod
    def validate_max_results(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("max_results must be a positive integer string")

        if int(value) < 1:
            raise ValueError("max_results must be greater than zero")

        return value
