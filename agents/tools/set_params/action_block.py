from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from agents.tools.registry import register_tool
from agents.tools.set_params import run_set_params_follow_up
from agents.tools.types import ActionBlock, ParsedActions
from core.schemas.graph_edit_api import GraphEdit, GraphEditAction
from core.schemas.primitives import JsonValue


def _validate_non_empty(value: str) -> str:
    value = value.strip()

    if not value:
        raise ValueError("value must not be empty")

    return value


class SetParamsGraphEditActionBlock(ActionBlock[GraphEditAction]):
    """Base class for set-params actions represented as GraphEdit values."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    expected_action: ClassVar[GraphEditAction] = "set_params"

    @model_validator(mode="after")
    def validate_set_params_graph_edit(
        self,
    ) -> "SetParamsGraphEditActionBlock":
        if self.action != self.expected_action:
            raise ValueError(
                f"Expected action {self.expected_action!r}, "
                f"got {self.action!r}"
            )

        GraphEdit.model_validate(self.as_json_object())
        return self

    def to_graph_edit(self) -> GraphEdit:
        return GraphEdit.model_validate(self.as_json_object())


class SetParamsActionBlock(SetParamsGraphEditActionBlock):
    """Set or update parameters for an existing unit."""

    id: str
    new_params: dict[str, JsonValue]

    _validate_id = field_validator("id")(_validate_non_empty)


def handle_set_params_action(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, SetParamsActionBlock):
        raise TypeError(
            "Expected a set-params graph-edit action block, "
            f"got {type(block).__name__}"
        )

    actions.edits.append(block.to_graph_edit())


def register_set_params_tool() -> None:
    register_tool(
        "set_params",
        run_set_params_follow_up,
        action_blocks={
            SetParamsActionBlock.expected_action: SetParamsActionBlock,
        },
        action_handlers={
            SetParamsActionBlock.expected_action: handle_set_params_action,
        },
    )


register_set_params_tool()
