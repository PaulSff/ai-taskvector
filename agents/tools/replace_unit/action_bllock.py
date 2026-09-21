from typing import ClassVar

from pydantic import BaseModel, ConfigDict, model_validator

from agents.tools.registry import register_tool
from agents.tools.replace_unit import run_replace_unit_follow_up
from agents.tools.types import ActionBlock, ParsedActions
from core.schemas.graph_edit_api import (
    FindUnit,
    GraphEdit,
    GraphEditAction,
    GraphEditUnit,
)


class ReplaceUnitActionBlock(ActionBlock[GraphEditAction]):
    """Replace a unit while preserving its existing graph connections."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    expected_action: ClassVar[GraphEditAction] = "replace_unit"

    find_unit: FindUnit
    replace_with: GraphEditUnit

    @model_validator(mode="after")
    def validate_replace_unit_graph_edit(self) -> "ReplaceUnitActionBlock":
        if self.action != self.expected_action:
            raise ValueError(
                f"Expected action {self.expected_action!r}, "
                f"got {self.action!r}"
            )

        if not self.find_unit.id.strip():
            raise ValueError("find_unit.id must not be empty")

        if not self.replace_with.id.strip():
            raise ValueError("replace_with.id must not be empty")

        if not self.replace_with.type.strip():
            raise ValueError("replace_with.type must not be empty")

        if self.find_unit.id == self.replace_with.id:
            raise ValueError(
                "find_unit.id and replace_with.id must be different"
            )

        GraphEdit.model_validate(self.as_json_object())
        return self

    def to_graph_edit(self) -> GraphEdit:
        return GraphEdit.model_validate(self.as_json_object())


_REPLACE_UNIT_ACTION_BLOCK_TYPES = (
    ReplaceUnitActionBlock,
)


def handle_replace_unit_action(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, _REPLACE_UNIT_ACTION_BLOCK_TYPES):
        raise TypeError(
            "Expected a replace-unit graph-edit action block, "
            f"got {type(block).__name__}"
        )

    actions.edits.append(block.to_graph_edit())


def register_replace_unit_tool() -> None:
    register_tool(
        "replace_unit",
        run_replace_unit_follow_up,
        action_blocks={
            action_block_type.expected_action: action_block_type
            for action_block_type in _REPLACE_UNIT_ACTION_BLOCK_TYPES
        },
        action_handlers={
            action_block_type.expected_action: handle_replace_unit_action
            for action_block_type in _REPLACE_UNIT_ACTION_BLOCK_TYPES
        },
    )


register_replace_unit_tool()
