from typing import ClassVar, Protocol, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from core.schemas import ProcessGraph, TodoTask
from core.schemas.graph_edit_api import (
    GraphEdit,
    MultipleEditsSequential,
)
from core.schemas.primitives import WorkflowInputs


class ReplyToIncomingMessagePayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    chat_id: str | int = Field(...)


class IncompleteTaskResult(TypedDict):
    todo_list_id: str
    task: TodoTask


# Canonical graph edit model is the single source of truth for all edits,
# including todo-list edits.
type TodoEdit = GraphEdit
type TodoParams = TodoEdit | MultipleEditsSequential


def todo_params_to_workflow_inputs(
    params: TodoParams,
) -> WorkflowInputs:
    """
    Convert canonical todo graph edits into workflow input overrides.
    """
    if isinstance(params, MultipleEditsSequential):
        converted = params.model_dump(
            by_alias=True,
            exclude_none=True,
        )
    else:
        converted = params.model_dump(
            by_alias=True,
            exclude_none=True,
        )

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
