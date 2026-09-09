from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from agents.tools.list_dir import run_list_dir_follow_up
from agents.tools.registry import register_tool
from agents.tools.types import ActionBlock, ParsedActions


class ListDirActionBlock(
    ActionBlock[Literal["list_dir"]]
):
    """List the contents of a local directory."""

    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("path must not be empty")

        return value


def handle_list_dir(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, ListDirActionBlock):
        raise TypeError(
            "Expected a list_dir action block, "
            f"got {type(block).__name__}"
        )

    actions.add_tool_action(
        "list_dir",
        block.as_json_object(),
    )


def register_list_dir_tool() -> None:
    register_tool(
        "list_dir",
        run_list_dir_follow_up,
        action_blocks={
            "list_dir": ListDirActionBlock,
        },
        action_handlers={
            "list_dir": handle_list_dir,
        },
    )


register_list_dir_tool()
