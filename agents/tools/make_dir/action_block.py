from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from agents.tools.make_dir import run_make_dir_follow_up
from agents.tools.registry import register_tool
from agents.tools.types import ActionBlock, ParsedActions


class MakeDirActionBlock(
    ActionBlock[Literal["make_dir"]]
):
    """Create a new directory."""

    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("path must not be empty")

        return value


def handle_make_dir(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, MakeDirActionBlock):
        raise TypeError(
            "Expected a make_dir action block, "
            f"got {type(block).__name__}"
        )

    actions.add_tool_action(
        "make_dir",
        block.as_json_object(),
    )


def register_make_dir_tool() -> None:
    register_tool(
        "make_dir",
        run_make_dir_follow_up,
        action_blocks={
            "make_dir": MakeDirActionBlock,
        },
        action_handlers={
            "make_dir": handle_make_dir,
        },
    )


register_make_dir_tool()
