from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from agents.tools.registry import register_action_block
from agents.tools.types import ActionBlock, ParsedActions


class ReadFileActionBlock(
    ActionBlock[Literal["read_file"]]
):
    """Read the contents of a file."""

    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("path must not be empty")

        return value


def handle_read_file(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, ReadFileActionBlock):
        raise TypeError(
            "Expected a read_file action block, "
            f"got {type(block).__name__}"
        )

    actions.add_tool_action(
        "read_file",
        block.as_json_object(),
    )


def register_read_file_action_blocks() -> None:
    register_action_block(
        "read_file",
        ReadFileActionBlock,
        handler=handle_read_file,
    )
