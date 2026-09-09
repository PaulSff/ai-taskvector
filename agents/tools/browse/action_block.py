from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents.tools.browse import run_browse_follow_up
from agents.tools.registry import register_tool
from agents.tools.types import ActionBlock, ParsedActions


class BrowseActionBlock(ActionBlock[Literal["browse"]]):
    """Read a web page from an HTML or URL source."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1)


def handle_browse(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, BrowseActionBlock):
        raise TypeError(
            f"Expected BrowseActionBlock, got {type(block).__name__}"
        )

    actions.add_tool_action(
        "browse",
        block.as_json_object(),
    )


def register_browse_tool() -> None:
    register_tool(
        "browse",
        run_browse_follow_up,
        action_blocks={
            "browse": BrowseActionBlock,
        },
        action_handlers={
            "browse": handle_browse,
        },
    )


register_browse_tool()
