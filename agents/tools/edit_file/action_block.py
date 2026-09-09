# agents/tools/action_blocks/edit_file.py

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agents.tools.edit_file import run_edit_file_follow_up
from agents.tools.registry import register_tool
from agents.tools.types import ActionBlock, ParsedActions


class EditFileReplacement(BaseModel):
    """A single find-and-replace operation."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    line_num_ref: int = Field(
        description="Approximate line number near the replacement region.",
    )
    find: str
    replace_with: str

    @field_validator("find")
    @classmethod
    def validate_find(cls, value: str) -> str:
        if not value:
            raise ValueError("find must not be empty")

        return value

    @field_validator("replace_with")
    @classmethod
    def normalize_replace_with(cls, value: str) -> str:
        # An empty string is valid and means delete the matched text.
        return value

    @field_validator("line_num_ref")
    @classmethod
    def validate_line_num_ref(cls, value: int) -> int:
        if value < 1:
            raise ValueError("line_num_ref must be greater than zero")

        return value


class EditFileTarget(BaseModel):
    """The file being edited and its replacement operations."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    file_name: str
    replacements: dict[str, EditFileReplacement]

    @field_validator("file_name")
    @classmethod
    def validate_file_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("file_name must not be empty")

        return value

    @field_validator("replacements")
    @classmethod
    def validate_replacements(
        cls,
        value: dict[str, EditFileReplacement],
    ) -> dict[str, EditFileReplacement]:
        if not value:
            raise ValueError("replacements must not be empty")

        return value


class EditFileParserOutput(BaseModel):
    """Normalized edit-file action stored in ParsedActions."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    action: Literal["edit_file"]
    output_dir: str
    file: EditFileTarget

    @field_validator("output_dir")
    @classmethod
    def validate_output_dir(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("output_dir must not be empty")

        return value


class EditFileActionBlock(
    ActionBlock[Literal["edit_file"]]
):
    """Apply one or more replacements to a file."""

    output_dir: str
    file: EditFileTarget

    @field_validator("output_dir")
    @classmethod
    def validate_output_dir(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("output_dir must not be empty")

        return value


def handle_edit_file(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, EditFileActionBlock):
        raise TypeError(
            f"Expected EditFileActionBlock, got {type(block).__name__}"
        )

    actions.add_tool_action(
        "edit_file",
        block.as_json_object(),
    )


def register_edit_file_tool() -> None:
    register_tool(
        "edit_file",
        run_edit_file_follow_up,
        action_blocks={
            "edit_file": EditFileActionBlock,
        },
        action_handlers={
            "edit_file": handle_edit_file,
        },
    )



def get_edit_file_outputs(
    actions: ParsedActions,
) -> list[EditFileParserOutput]:
    return [
        EditFileParserOutput.model_validate(raw_action)
        for raw_action in actions.get_tool_actions("edit_file")
    ]

register_edit_file_tool()
