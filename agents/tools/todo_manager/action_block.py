
from typing import Literal

from pydantic import field_validator

from agents.tools.types import ActionBlock


def _validate_non_empty(value: str) -> str:
    value = value.strip()

    if not value:
        raise ValueError("value must not be empty")

    return value


class AddTodoListActionBlock(
    ActionBlock[Literal["add_todo_list"]]
):
    """Add a new TODO list."""

    id: str
    title: str

    _validate_id = field_validator("id")(_validate_non_empty)
    _validate_title = field_validator("title")(_validate_non_empty)


class RemoveTodoListActionBlock(
    ActionBlock[Literal["remove_todo_list"]]
):
    """Remove a TODO list."""

    id: str

    _validate_id = field_validator("id")(_validate_non_empty)


class AddTaskActionBlock(
    ActionBlock[Literal["add_task"]]
):
    """Add a task to a TODO list."""

    todo_list_id: str
    text: str

    _validate_todo_list_id = field_validator("todo_list_id")(
        _validate_non_empty
    )
    _validate_text = field_validator("text")(_validate_non_empty)


class RemoveTaskActionBlock(
    ActionBlock[Literal["remove_task"]]
):
    """Remove a task from a TODO list."""

    task_id: str
    todo_list_id: str

    _validate_ids = field_validator("task_id", "todo_list_id")(
        _validate_non_empty
    )


class MarkCompletedActionBlock(
    ActionBlock[Literal["mark_completed"]]
):
    """Mark a TODO task as completed or incomplete."""

    task_id: str
    todo_list_id: str
    completed: bool

    _validate_ids = field_validator("task_id", "todo_list_id")(
        _validate_non_empty
    )


class SetImplementerActionBlock(
    ActionBlock[Literal["set_implementer"]]
):
    """Set or clear the implementer assigned to a task."""

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


class SetDeadlineActionBlock(
    ActionBlock[Literal["set_deadline"]]
):
    """Set the estimated completion time for a task in seconds."""

    task_id: str
    deadline: int
    todo_list_id: str

    _validate_ids = field_validator("task_id", "todo_list_id")(
        _validate_non_empty
    )

    @field_validator("deadline")
    @classmethod
    def validate_deadline(cls, value: int) -> int:
        if value < 0:
            raise ValueError("deadline must not be negative")

        return value


class SetCuratorActionBlock(
    ActionBlock[Literal["set_curator"]]
):
    """Set or clear the curator assigned to a task."""

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


class SetTodoListTitleActionBlock(
    ActionBlock[Literal["set_todo_list_title"]]
):
    """Change the title of a TODO list."""

    todo_list_id: str
    title: str

    _validate_todo_list_id = field_validator("todo_list_id")(
        _validate_non_empty
    )
    _validate_title = field_validator("title")(_validate_non_empty)
