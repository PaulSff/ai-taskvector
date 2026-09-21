from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from agents.tools.registry import register_tool
from agents.tools.remove_unit import run_remove_unit_follow_up
from agents.tools.types import ActionBlock, ParsedActions
from core.schemas.graph_edit_api import GraphEdit, GraphEditAction


def _validate_non_empty(value: str) -> str:
    value = value.strip()

    if not value:
        raise ValueError("value must not be empty")

    return value


class RemoveUnitGraphEditActionBlock(ActionBlock[GraphEditAction]):
    """Base class for remove-unit actions represented as GraphEdit values."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    expected_action: ClassVar[GraphEditAction] = "remove_unit"

    @model_validator(mode="after")
    def validate_remove_unit_graph_edit(
        self,
    ) -> "RemoveUnitGraphEditActionBlock":
        if self.action != self.expected_action:
            raise ValueError(
                f"Expected action {self.expected_action!r}, "
                f"got {self.action!r}"
            )

        GraphEdit.model_validate(self.as_json_object())
        return self

    def to_graph_edit(self) -> GraphEdit:
        return GraphEdit.model_validate(self.as_json_object())


class RemoveUnitActionBlock(RemoveUnitGraphEditActionBlock):
    """Remove a unit from the process graph."""

    unit_id: str

    _validate_unit_id = field_validator("unit_id")(_validate_non_empty)


def handle_remove_unit_action(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, RemoveUnitActionBlock):
        raise TypeError(
            "Expected a remove-unit graph-edit action block, "
            f"got {type(block).__name__}"
        )

    actions.edits.append(block.to_graph_edit())


def register_remove_unit_tool() -> None:
    register_tool(
        "remove_unit",
        run_remove_unit_follow_up,
        action_blocks={
            RemoveUnitActionBlock.expected_action: RemoveUnitActionBlock,
        },
        action_handlers={
            RemoveUnitActionBlock.expected_action: handle_remove_unit_action,
        },
    )


register_remove_unit_tool()
