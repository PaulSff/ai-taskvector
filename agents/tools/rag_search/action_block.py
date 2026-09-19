"""
Smoke the action block with the following:

python - <<'PY'
from pydantic import ValidationError

# Importing this module registers the tool via register_rag_search_tool()
from agents.tools.rag_search.action_block import SearchActionBlock

payload = {
    "action": "search",
    "query": "cable documentation",
    "max_results": "10",
}

try:
    block = SearchActionBlock.model_validate(payload)
    print("VALID")
    print(block.model_dump())
except ValidationError as exc:
    print("INVALID")
    for error in exc.errors(include_url=False):
        print(error)
PY

"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from agents.tools.rag_search import run_rag_search_follow_up
from agents.tools.registry import register_tool
from agents.tools.types import ActionBlock, ParsedActions


class SearchActionBlock(
    ActionBlock[Literal["search"]]
):
    """Search the knowledge base."""

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


def handle_search(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, SearchActionBlock):
        raise TypeError(
            "Expected a search action block, "
            f"got {type(block).__name__}"
        )

    actions.add_tool_action(
        "search",
        block.as_json_object(),
    )


def register_rag_search_tool() -> None:
    register_tool(
        "rag_search",
        run_rag_search_follow_up,
        action_blocks={
            "search": SearchActionBlock,
        },
        action_handlers={
            "search": handle_search,
        },
    )


register_rag_search_tool()
