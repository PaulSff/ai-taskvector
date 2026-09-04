from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from agents.tools.registry import register_action_block
from agents.tools.types import ActionBlock, ParsedActions
from core.schemas.graph_edit_api import GraphEdit, GraphEditAction


def _validate_non_empty(value: str) -> str:
    value = value.strip()

    if not value:
        raise ValueError("value must not be empty")

    return value


class CommentGraphEditActionBlock(ActionBlock[GraphEditAction]):
    """Base class for comment actions represented as GraphEdit values."""

    model_config = ConfigDict(
        extra="allow",
        strict=True,
    )

    expected_action: ClassVar[GraphEditAction]

    @model_validator(mode="after")
    def validate_comment_graph_edit(self) -> "CommentGraphEditActionBlock":
        if self.action != self.expected_action:
            raise ValueError(
                f"Expected action {self.expected_action!r}, "
                f"got {self.action!r}"
            )

        GraphEdit.model_validate(self.as_json_object())
        return self

    def to_graph_edit(self) -> GraphEdit:
        return GraphEdit.model_validate(self.as_json_object())


class AddCommentActionBlock(CommentGraphEditActionBlock):
    """Leave a note on the process graph."""

    expected_action: ClassVar[GraphEditAction] = "add_comment"

    info: str

    _validate_info = field_validator("info")(_validate_non_empty)


class RemoveCommentActionBlock(CommentGraphEditActionBlock):
    """Remove an existing comment from the process graph."""

    expected_action: ClassVar[GraphEditAction] = "remove_comment"

    comment_id: str

    _validate_comment_id = field_validator("comment_id")(
        _validate_non_empty
    )


_COMMENT_ACTION_BLOCK_TYPES = (
    AddCommentActionBlock,
    RemoveCommentActionBlock,
)


def handle_comment_action(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, _COMMENT_ACTION_BLOCK_TYPES):
        raise TypeError(
            "Expected a comment graph-edit action block, "
            f"got {type(block).__name__}"
        )

    actions.edits.append(block.to_graph_edit())


def register_comment_action_blocks() -> None:
    for action_block_type in _COMMENT_ACTION_BLOCK_TYPES:
        register_action_block(
            action_block_type.expected_action,
            action_block_type,
            handler=handle_comment_action,
        )
