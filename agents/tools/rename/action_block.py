
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from agents.tools.registry import register_action_block, register_tool
from agents.tools.rename import run_rename_follow_up
from agents.tools.types import ActionBlock, ParsedActions


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


def handle_rename(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, RenameActionBlock):
        raise TypeError(
            "Expected a rename action block, "
            f"got {type(block).__name__}"
        )

    actions.add_tool_action(
        "rename",
        block.as_json_object(),
    )


def register_rename_tool() -> None:
    register_tool(
        "rename",
        run_rename_follow_up,
        action_blocks={
            "rename": RenameActionBlock,
        },
        action_handlers={
            "rename": handle_rename,
        },
    )


register_rename_tool()
