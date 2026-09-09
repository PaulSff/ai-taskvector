from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from agents.tools.registry import register_tool
from agents.tools.todo_manager import run_todo_manager_follow_up
from agents.tools.types import ActionBlock, ParsedActions
from core.schemas.graph_edit_api import GraphEdit, GraphEditAction


def _validate_non_empty(value: str) -> str:
    value = value.strip()

    if not value:
        raise ValueError("value must not be empty")

    return value


class TodoGraphEditActionBlock(ActionBlock[GraphEditAction]):
    """Base class for TODO actions represented as GraphEdit values."""

    model_config = ConfigDict(
        extra="allow",
        strict=True,
    )

    expected_action: ClassVar[GraphEditAction]

    @model_validator(mode="after")
    def validate_todo_graph_edit(self) -> TodoGraphEditActionBlock:
        if self.action != self.expected_action:
            raise ValueError(
                f"Expected action {self.expected_action!r}, "
                f"got {self.action!r}"
            )

        GraphEdit.model_validate(self.as_json_object())
        return self

    def to_graph_edit(self) -> GraphEdit:
        return GraphEdit.model_validate(self.as_json_object())


class AddTodoListActionBlock(TodoGraphEditActionBlock):
    """Add a new TODO list."""

    expected_action: ClassVar[GraphEditAction] = "add_todo_list"

    id: str
    title: str

    _validate_id = field_validator("id")(_validate_non_empty)
    _validate_title = field_validator("title")(_validate_non_empty)


class RemoveTodoListActionBlock(TodoGraphEditActionBlock):
    """Remove a TODO list."""

    expected_action: ClassVar[GraphEditAction] = "remove_todo_list"

    id: str

    _validate_id = field_validator("id")(_validate_non_empty)


class AddTaskActionBlock(TodoGraphEditActionBlock):
    """Add a task to a TODO list."""

    expected_action: ClassVar[GraphEditAction] = "add_task"

    todo_list_id: str
    text: str

    _validate_todo_list_id = field_validator("todo_list_id")(
        _validate_non_empty
    )
    _validate_text = field_validator("text")(_validate_non_empty)


class RemoveTaskActionBlock(TodoGraphEditActionBlock):
    """Remove a task from a TODO list."""

    expected_action: ClassVar[GraphEditAction] = "remove_task"

    task_id: str
    todo_list_id: str

    _validate_ids = field_validator("task_id", "todo_list_id")(
        _validate_non_empty
    )


class MarkCompletedActionBlock(TodoGraphEditActionBlock):
    """Mark a TODO task as completed or incomplete."""

    expected_action: ClassVar[GraphEditAction] = "mark_completed"

    task_id: str
    todo_list_id: str
    completed: bool

    _validate_ids = field_validator("task_id", "todo_list_id")(
        _validate_non_empty
    )


class SetImplementerActionBlock(TodoGraphEditActionBlock):
    """Set or clear the implementer assigned to a task."""

    expected_action: ClassVar[GraphEditAction] = "set_implementer"

    task_id: str
    implementer: str | None
    todo_list_id: str

    _validate_ids = field_validator("task_id", "todo_list_id")(
        _validate_non_empty
    )

    @field_validator("implementer")
    @classmethod
    def validate_implementer(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return _validate_non_empty(value)


class SetDeadlineActionBlock(TodoGraphEditActionBlock):
    """Set or clear the estimated completion time for a task."""

    expected_action: ClassVar[GraphEditAction] = "set_deadline"

    task_id: str
    deadline: int | None
    todo_list_id: str

    _validate_ids = field_validator("task_id", "todo_list_id")(
        _validate_non_empty
    )

    @field_validator("deadline")
    @classmethod
    def validate_deadline(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("deadline must not be negative")

        return value


class SetCuratorActionBlock(TodoGraphEditActionBlock):
    """Set or clear the curator assigned to a task."""

    expected_action: ClassVar[GraphEditAction] = "set_curator"

    task_id: str
    curator: str | None
    todo_list_id: str

    _validate_ids = field_validator("task_id", "todo_list_id")(
        _validate_non_empty
    )

    @field_validator("curator")
    @classmethod
    def validate_curator(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return _validate_non_empty(value)


class SetTodoListTitleActionBlock(TodoGraphEditActionBlock):
    """Change the title of a TODO list."""

    expected_action: ClassVar[GraphEditAction] = "set_todo_list_title"

    todo_list_id: str
    title: str

    _validate_todo_list_id = field_validator("todo_list_id")(
        _validate_non_empty
    )
    _validate_title = field_validator("title")(_validate_non_empty)


_TODO_ACTION_BLOCK_TYPES = (
    AddTodoListActionBlock,
    RemoveTodoListActionBlock,
    AddTaskActionBlock,
    RemoveTaskActionBlock,
    MarkCompletedActionBlock,
    SetImplementerActionBlock,
    SetDeadlineActionBlock,
    SetCuratorActionBlock,
    SetTodoListTitleActionBlock,
)


def handle_todo_action(
    actions: ParsedActions,
    block: BaseModel,
) -> None:
    if not isinstance(block, _TODO_ACTION_BLOCK_TYPES):
        raise TypeError(
            "Expected a TODO graph-edit action block, "
            f"got {type(block).__name__}"
        )

    actions.edits.append(block.to_graph_edit())


def register_todo_tool() -> None:
    action_blocks = {
        action_block_type.expected_action: action_block_type
        for action_block_type in _TODO_ACTION_BLOCK_TYPES
    }

    action_handlers = {
        action_block_type.expected_action: handle_todo_action
        for action_block_type in _TODO_ACTION_BLOCK_TYPES
    }

    register_tool(
        "todo",
        run_todo_manager_follow_up,
        action_blocks=action_blocks,
        action_handlers=action_handlers,
    )


register_todo_tool()
