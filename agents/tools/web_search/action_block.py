from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from agents.tools.registry import register_tool
from agents.tools.types import ActionBlock, ParsedActions
from agents.tools.web_search import run_web_search_follow_up


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
            raise ValueError(
                "max_results must be a positive integer string"
            )

        if int(value) < 1:
            raise ValueError("max_results must be greater than zero")

        return value


def handle_web_search(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, WebSearchActionBlock):
        raise TypeError(
            "Expected a web_search action block, "
            f"got {type(block).__name__}"
        )

    actions.add_tool_action(
        "web_search",
        block.as_json_object(),
    )


def register_web_search_tool() -> None:
    register_tool(
        "web_search",
        run_web_search_follow_up,
        action_blocks={
            "web_search": WebSearchActionBlock,
        },
        action_handlers={
            "web_search": handle_web_search,
        },
    )


register_web_search_tool()
