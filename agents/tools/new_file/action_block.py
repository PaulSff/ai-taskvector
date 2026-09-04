from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from agents.tools.registry import register_action_block
from agents.tools.types import ActionBlock, ParsedActions


class NewFileSpec(BaseModel):
    """Specification for the file to create."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    output_format: str
    file_name: str
    content: str

    @field_validator("output_format", "file_name")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("value must not be empty")

        return value

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        # Empty content is valid when creating an empty file.
        return value


class NewFileActionBlock(
    ActionBlock[Literal["new_file"]]
):
    """Generate a new file in a specified folder."""

    output_dir: str
    file: NewFileSpec

    @field_validator("output_dir")
    @classmethod
    def validate_output_dir(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("output_dir must not be empty")

        return value


def handle_new_file(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, NewFileActionBlock):
        raise TypeError(
            "Expected a new_file action block, "
            f"got {type(block).__name__}"
        )

    actions.add_tool_action(
        "new_file",
        block.as_json_object(),
    )


def register_new_file_action_blocks() -> None:
    register_action_block(
        "new_file",
        NewFileActionBlock,
        handler=handle_new_file,
    )
