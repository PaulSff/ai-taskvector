from typing import ClassVar

from pydantic import BaseModel, ConfigDict, model_validator

from agents.tools.add_unit import run_add_unit_follow_up
from agents.tools.registry import register_tool
from agents.tools.types import ActionBlock, ParsedActions
from core.schemas.graph_edit_api import (
    GraphEdit,
    GraphEditAction,
    GraphEditUnit,
)


class UnitGraphEditActionBlock(ActionBlock[GraphEditAction]):
    """Base class for unit actions represented as GraphEdit values."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    expected_action: ClassVar[GraphEditAction]

    @model_validator(mode="after")
    def validate_unit_graph_edit(self) -> "UnitGraphEditActionBlock":
        if self.action != self.expected_action:
            raise ValueError(
                f"Expected action {self.expected_action!r}, "
                f"got {self.action!r}"
            )

        GraphEdit.model_validate(self.as_json_object())
        return self

    def to_graph_edit(self) -> GraphEdit:
        return GraphEdit.model_validate(self.as_json_object())


class AddUnitActionBlock(UnitGraphEditActionBlock):
    """Add a unit to the process graph."""

    expected_action: ClassVar[GraphEditAction] = "add_unit"

    unit: GraphEditUnit


_UNIT_ACTION_BLOCK_TYPES = (
    AddUnitActionBlock,
)


def handle_unit_action(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, _UNIT_ACTION_BLOCK_TYPES):
        raise TypeError(
            "Expected a unit graph-edit action block, "
            f"got {type(block).__name__}"
        )

    actions.edits.append(block.to_graph_edit())


def register_add_unit_tool() -> None:
    register_tool(
        "add_unit",
        run_add_unit_follow_up,
        action_blocks={
            action_block_type.expected_action: action_block_type
            for action_block_type in _UNIT_ACTION_BLOCK_TYPES
        },
        action_handlers={
            action_block_type.expected_action: handle_unit_action
            for action_block_type in _UNIT_ACTION_BLOCK_TYPES
        },
    )


register_add_unit_tool()
