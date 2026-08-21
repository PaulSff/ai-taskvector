from typing import Literal, Protocol, TypedDict

from core.schemas import ProcessGraph, TodoTask


class IncompleteTaskResult(TypedDict):
    todo_list_id: str
    task: TodoTask


class AddTodoListEdit(TypedDict):
    action: Literal["add_todo_list"]
    id: str
    title: str


class AddTaskEdit(TypedDict):
    action: Literal["add_task"]
    todo_list_id: str
    text: str


class RemoveTaskEdit(TypedDict):
    action: Literal["remove_task"]
    todo_list_id: str
    task_id: str


class SetDeadlineEdit(TypedDict):
    action: Literal["set_deadline"]
    todo_list_id: str
    task_id: str
    deadline: str | None


type TodoEdit = (
    AddTodoListEdit
    | AddTaskEdit
    | RemoveTaskEdit
    | SetDeadlineEdit
)

class MultipleEditsSequential(TypedDict):
    Multiple_edits_sequential: list[TodoEdit]


type TodoParams = TodoEdit | MultipleEditsSequential


class QueueAddTask(Protocol):
    def __call__(
        self,
        *,
        current: ProcessGraph,
        task_text: str,
        queued_task_texts: set[str],
        edits_to_apply: list[TodoEdit],
        list_id: str,
    ) -> None:
        ...


class EnsureTodoListIfMissing(Protocol):
    def __call__(
        self,
        *,
        current: ProcessGraph,
        edits_to_apply: list[TodoEdit],
        ensured_todo_list: bool,
        list_id: str,
        title: str,
    ) -> None:
        ...
