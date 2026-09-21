from typing import ClassVar

from pydantic import BaseModel, ConfigDict, model_validator

from agents.tools.registry import register_tool
from agents.tools.replace_graph import run_replace_graph_follow_up
from agents.tools.types import ActionBlock, ParsedActions
from core.schemas.graph_edit_api import GraphEdit, GraphEditAction


class ReplaceGraphActionBlock(ActionBlock[GraphEditAction]):
    """Replace the entire process graph with a new set of units and connections."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    expected_action: ClassVar[GraphEditAction] = "replace_graph"

    units: list[dict]
    connections: list[dict]

    @model_validator(mode="after")
    def validate_replace_graph(self) -> "ReplaceGraphActionBlock":
        if self.action != self.expected_action:
            raise ValueError(
                f"Expected action {self.expected_action!r}, "
                f"got {self.action!r}"
            )

        for index, unit in enumerate(self.units):
            self._validate_unit(unit, index)

        for index, connection in enumerate(self.connections):
            self._validate_connection(connection, index)

        GraphEdit.model_validate(self.as_json_object())
        return self

    @staticmethod
    def _validate_unit(unit: dict, index: int) -> None:
        required_fields = {"id", "type", "controllable"}

        missing_fields = required_fields - unit.keys()
        if missing_fields:
            raise ValueError(
                f"units[{index}] is missing required fields: "
                f"{sorted(missing_fields)}"
            )

        if not isinstance(unit["id"], str) or not unit["id"].strip():
            raise ValueError(
                f"units[{index}].id must be a non-empty string"
            )

        if not isinstance(unit["type"], str) or not unit["type"].strip():
            raise ValueError(
                f"units[{index}].type must be a non-empty string"
            )

        if not isinstance(unit["controllable"], bool):
            raise TypeError(
                f"units[{index}].controllable must be a boolean"
            )

        if "params" in unit and not isinstance(unit["params"], dict):
            raise ValueError(
                f"units[{index}].params must be an object"
            )

    @staticmethod
    def _validate_connection(connection: dict, index: int) -> None:
        required_fields = {"from", "to"}

        missing_fields = required_fields - connection.keys()
        if missing_fields:
            raise ValueError(
                f"connections[{index}] is missing required fields: "
                f"{sorted(missing_fields)}"
            )

        for field in ("from", "to"):
            value = connection[field]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"connections[{index}].{field} "
                    "must be a non-empty string"
                )

        for field in ("from_port", "to_port"):
            if field in connection and not isinstance(connection[field], str):
                raise ValueError(
                    f"connections[{index}].{field} must be a string"
                )

    def to_graph_edit(self) -> GraphEdit:
        return GraphEdit.model_validate(self.as_json_object())


_REPLACE_GRAPH_ACTION_BLOCK_TYPES = (
    ReplaceGraphActionBlock,
)


def handle_replace_graph_action(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, _REPLACE_GRAPH_ACTION_BLOCK_TYPES):
        raise TypeError(
            "Expected a replace-graph action block, "
            f"got {type(block).__name__}"
        )

    actions.edits.append(block.to_graph_edit())


def register_replace_graph_tool() -> None:
    register_tool(
        "replace_graph",
        run_replace_graph_follow_up,
        action_blocks={
            action_block_type.expected_action: action_block_type
            for action_block_type in _REPLACE_GRAPH_ACTION_BLOCK_TYPES
        },
        action_handlers={
            action_block_type.expected_action: handle_replace_graph_action
            for action_block_type in _REPLACE_GRAPH_ACTION_BLOCK_TYPES
        },
    )


register_replace_graph_tool()
