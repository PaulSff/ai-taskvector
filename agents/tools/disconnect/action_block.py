from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agents.tools.disconnect import run_disconnect_follow_up
from agents.tools.registry import register_tool
from agents.tools.types import ActionBlock, ParsedActions
from core.schemas.graph_edit_api import GraphEdit, GraphEditAction


class DisconnectActionBlock(ActionBlock[GraphEditAction]):
    """Disconnect two units in the process graph."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=True,
    )

    expected_action: ClassVar[GraphEditAction] = "disconnect"

    from_id: str = Field(
        ...,
        alias="from",
        description="Source unit id",
    )
    to_id: str = Field(
        ...,
        alias="to",
        description="Target unit id",
    )
    from_port: str | None = Field(
        default=None,
        description="Optional source output port index",
    )
    to_port: str | None = Field(
        default=None,
        description="Optional target input port index",
    )

    @model_validator(mode="after")
    def validate_disconnect_graph_edit(self) -> "DisconnectActionBlock":
        if self.action != self.expected_action:
            raise ValueError(
                f"Expected action {self.expected_action!r}, "
                f"got {self.action!r}"
            )

        if not self.from_id.strip():
            raise ValueError("from must not be empty")

        if not self.to_id.strip():
            raise ValueError("to must not be empty")

        GraphEdit.model_validate(self.as_json_object())
        return self

    def to_graph_edit(self) -> GraphEdit:
        return GraphEdit.model_validate(self.as_json_object())


_DISCONNECT_ACTION_BLOCK_TYPES = (
    DisconnectActionBlock,
)


def handle_disconnect_action(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, _DISCONNECT_ACTION_BLOCK_TYPES):
        raise TypeError(
            "Expected a disconnect graph-edit action block, "
            f"got {type(block).__name__}"
        )

    actions.edits.append(block.to_graph_edit())


def register_disconnect_tool() -> None:
    register_tool(
        "disconnect",
        run_disconnect_follow_up,
        action_blocks={
            action_block_type.expected_action: action_block_type
            for action_block_type in _DISCONNECT_ACTION_BLOCK_TYPES
        },
        action_handlers={
            action_block_type.expected_action: handle_disconnect_action
            for action_block_type in _DISCONNECT_ACTION_BLOCK_TYPES
        },
    )


register_disconnect_tool()
