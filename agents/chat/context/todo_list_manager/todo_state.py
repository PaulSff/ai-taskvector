from typing import ClassVar, Literal, Protocol, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from core.normalizer.shared import to_json_value
from core.schemas import ProcessGraph, TodoTask
from core.schemas.primitives import WorkflowInputs


class ReplyToIncomingMessagePayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    chat_id: str | int = Field(...)

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

# This converter constructs params overrides for todo_list unit
# operating within todo_list tool workflow
def todo_params_to_workflow_inputs(
    params: TodoParams,
) -> WorkflowInputs:
    converted = to_json_value(params)

    if not isinstance(converted, dict):
        raise TypeError("TodoParams must convert to a JSON object")

    return {
        "todo_list": converted,
    }


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
