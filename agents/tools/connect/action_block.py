from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from agents.tools.connect import run_connect_follow_up
from agents.tools.registry import register_tool
from agents.tools.types import ActionBlock, ParsedActions
from core.schemas.graph_edit_api import GraphEdit, GraphEditAction


def _validate_non_empty(value: str) -> str:
    value = value.strip()

    if not value:
        raise ValueError("value must not be empty")

    return value


def _validate_port_index(value: str) -> str:
    value = value.strip()

    if not value:
        raise ValueError("port index must not be empty")

    if not value.isdigit():
        raise ValueError("port index must be a non-negative integer string")

    return value


class ConnectGraphEditActionBlock(ActionBlock[GraphEditAction]):
    """Base class for connect actions represented as GraphEdit values."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        strict=True,
    )

    expected_action: ClassVar[GraphEditAction] = "connect"

    @model_validator(mode="after")
    def validate_connect_graph_edit(
        self,
    ) -> "ConnectGraphEditActionBlock":
        if self.action != self.expected_action:
            raise ValueError(
                f"Expected action {self.expected_action!r}, "
                f"got {self.action!r}"
            )

        GraphEdit.model_validate(self.as_json_object())
        return self

    def to_graph_edit(self) -> GraphEdit:
        return GraphEdit.model_validate(self.as_json_object())


class ConnectActionBlock(ConnectGraphEditActionBlock):
    """Connect two units in the process graph."""

    from_id: str
    to_id: str
    from_port: str = "0"
    to_port: str = "0"

    _validate_from_id = field_validator("from_id")(_validate_non_empty)
    _validate_to_id = field_validator("to_id")(_validate_non_empty)
    _validate_from_port = field_validator("from_port")(_validate_port_index)
    _validate_to_port = field_validator("to_port")(_validate_port_index)


def handle_connect_action(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, ConnectActionBlock):
        raise TypeError(
            "Expected a connect graph-edit action block, "
            f"got {type(block).__name__}"
        )

    actions.edits.append(block.to_graph_edit())


def register_connect_tool() -> None:
    register_tool(
        "connect",
        run_connect_follow_up,
        action_blocks={
            ConnectActionBlock.expected_action: ConnectActionBlock,
        },
        action_handlers={
            ConnectActionBlock.expected_action: handle_connect_action,
        },
    )


register_connect_tool()
