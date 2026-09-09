# agents/tools/action_blocks/delete.py

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from agents.tools.delete import run_delete_file_follow_up
from agents.tools.registry import register_tool
from agents.tools.types import ActionBlock, ParsedActions


class DeleteParserOutput(BaseModel):
    """Normalized delete action stored in ParsedActions."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["delete"]
    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("path must not be empty")

        return value


class DeleteActionBlock(
    ActionBlock[Literal["delete"]]
):
    """Delete a file or folder."""

    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("path must not be empty")

        return value


def handle_delete(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, DeleteActionBlock):
        raise TypeError(
            f"Expected DeleteActionBlock, got {type(block).__name__}"
        )

    actions.add_tool_action(
        "delete",
        block.as_json_object(),
    )


def register_delete_tool() -> None:
    register_tool(
        "delete",
        run_delete_file_follow_up,
        action_blocks={
            "delete": DeleteActionBlock,
        },
        action_handlers={
            "delete": handle_delete,
        },
    )


def get_delete_outputs(
    actions: ParsedActions,
) -> list[DeleteParserOutput]:
    return [
        DeleteParserOutput.model_validate(raw_action)
        for raw_action in actions.get_tool_actions("delete")
    ]


register_delete_tool()
