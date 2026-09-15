"""Todo-list edit: logic in unit, writes todo_lists into graph. Params: action, title, text, task_id, completed, todo_list_id, id, implementer, deadline, curator."""

from __future__ import annotations

from collections.abc import Callable
from typing import NotRequired, TypedDict, cast

from core.graph.batch_edits import apply_workflow_edits
from core.graph.todo_list import (
    add_task,
    create_new_todo_list,
    mark_completed,
    normalize_todo_lists,
    remove_task,
    set_curator,
    set_deadline,
    set_implementer,
    todo_lists_to_list,
)
from core.schemas import TodoList
from core.schemas.graph_edit_api import GraphEdit, MultipleEditsSequential
from core.schemas.primitives import JsonValue
from units.canonical.graph_edit._apply import get_graph_from_inputs
from units.registry import UnitSpec, register_unit

EDIT_INPUT_PORTS = [("data", "Any"), ("graph", "Any")]
EDIT_OUTPUT_PORTS = [("graph", "Any"), ("error", "Any")]

_ACTIONS = frozenset(
    {
        "add_todo_list",
        "add_task",
        "remove_task",
        "remove_todo_list",
        "mark_completed",
        "set_implementer",
        "set_deadline",
        "set_curator",
    }
)

GraphDict = dict[str, JsonValue]


class WorkflowEditResult(TypedDict):
    success: bool
    graph: NotRequired[GraphDict]
    error: NotRequired[str | None]


Params = dict[str, object]
Inputs = dict[str, object]
State = dict[str, object]
StepResult = dict[str, object]


def _require_edit_string(
    edit: GraphEdit,
    field: str,
) -> str:
    raw_value = cast(object, getattr(edit, field, None))

    if raw_value is None:
        raise ValueError(
            f"Incorrect format for {edit.action}: "
            + "missing required parameter: {field}"
        )

    value = str(raw_value).strip()

    if not value:
        raise ValueError(
            f"Incorrect format for {edit.action}: "
            + "{field} must be a non-empty string"
        )

    return value


def _optional_edit_string(
    edit: GraphEdit,
    field: str,
) -> str | None:
    raw_value = cast(object, getattr(edit, field, None))

    if raw_value is None:
        return None

    value = str(raw_value).strip()
    return value or None


def _replace_todo_list(
    todo_lists: list[TodoList],
    target_list_id: str,
    updater: Callable[[TodoList], TodoList],
) -> list[TodoList]:
    """Apply an update to one todo list without mutating the input."""
    result: list[TodoList] = []
    list_found = False

    for todo_list in todo_lists:
        if str(todo_list.id) == target_list_id:
            list_found = True
            result.append(updater(todo_list))
        else:
            result.append(todo_list)

    if not list_found:
        raise ValueError(f"Todo list not found: {target_list_id}")

    return result


def _apply_single_edit(
    todo_lists: list[TodoList | JsonValue] | None,
    edit: GraphEdit,
) -> list[JsonValue]:
    """
    Apply one validated GraphEdit to todo-list metadata.

    The result is returned as JSON-compatible dictionaries because graph
    metadata is typically serialized into ProcessGraph data.
    """
    # GraphEditAction may be a str Enum or a plain string.
    action: str = edit.action

    normalized_lists = normalize_todo_lists(todo_lists)

    if action == "add_todo_list":
        # GraphEdit has no list_id field, so id is used here.
        list_id = _optional_edit_string(edit, "id")

        updated_lists = create_new_todo_list(
            normalized_lists,
            title=edit.title,
            list_id=list_id,
        )
        return todo_lists_to_list(updated_lists)

    if action == "remove_todo_list":
        target_list_id = _require_edit_string(edit, "id")

        updated_lists = [
            todo_list
            for todo_list in normalized_lists
            if str(todo_list.id) != target_list_id
        ]

        if len(updated_lists) == len(normalized_lists):
            raise ValueError(f"Todo list not found: {target_list_id}")

        return todo_lists_to_list(updated_lists)

    task_actions = {
        "add_task",
        "remove_task",
        "mark_completed",
        "set_implementer",
        "set_deadline",
        "set_curator",
    }

    if action not in task_actions:
        raise ValueError(f"Unsupported todo action: {action}")

    if not normalized_lists:
        raise ValueError("No todo lists exist")

    requested_list_id = _optional_edit_string(edit, "todo_list_id")

    if requested_list_id is not None:
        target_list_id = requested_list_id
    elif len(normalized_lists) == 1:
        target_list_id = str(normalized_lists[0].id)
    else:
        raise ValueError(
            f"Incorrect format for {action}: "
            + "missing required parameter: todo_list_id "
            + "(todo list id)"
        )

    if action == "add_task":
        task_text = _require_edit_string(edit, "text")

        updated_lists = _replace_todo_list(
            normalized_lists,
            target_list_id,
            lambda todo_list: add_task(
                todo_list,
                task_text,
                task_id=_optional_edit_string(edit, "task_id"),
            ),
        )
        return todo_lists_to_list(updated_lists)

    task_id = _require_edit_string(edit, "task_id")

    if action == "remove_task":
        updated_lists = _replace_todo_list(
            normalized_lists,
            target_list_id,
            lambda todo_list: remove_task(todo_list, task_id),
        )
        return todo_lists_to_list(updated_lists)

    if action == "mark_completed":
        # GraphEdit already validates this as bool.
        updated_lists = _replace_todo_list(
            normalized_lists,
            target_list_id,
            lambda todo_list: mark_completed(
                todo_list,
                task_id,
                completed=edit.completed,
            ),
        )
        return todo_lists_to_list(updated_lists)

    if action == "set_implementer":
        updated_lists = _replace_todo_list(
            normalized_lists,
            target_list_id,
            lambda todo_list: set_implementer(
                todo_list,
                task_id,
                implementer=edit.implementer,
            ),
        )
        return todo_lists_to_list(updated_lists)

    if action == "set_deadline":
        updated_lists = _replace_todo_list(
            normalized_lists,
            target_list_id,
            lambda todo_list: set_deadline(
                todo_list,
                task_id,
                deadline=edit.deadline,
            ),
        )
        return todo_lists_to_list(updated_lists)

    # action == "set_curator"
    updated_lists = _replace_todo_list(
        normalized_lists,
        target_list_id,
        lambda todo_list: set_curator(
            todo_list,
            task_id,
            curator=edit.curator,
        ),
    )
    return todo_lists_to_list(updated_lists)


def _parse_graph_edit(value: object) -> GraphEdit:
    if isinstance(value, GraphEdit):
        return value

    if not isinstance(value, dict):
        raise TypeError(f"Invalid graph edit: {value!r}")

    return GraphEdit.model_validate(value)


def _single_edit_params(params: Params) -> dict[str, object]:
    return {
        key: value
        for key, value in params.items()
        if key != "Multiple_edits_sequential"
    }

def _as_workflow_edit_result(value: object) -> WorkflowEditResult:
    if not isinstance(value, dict):
        raise TypeError("Invalid workflow edit result")

    result_value = cast(dict[str, object], value)

    success = result_value.get("success")
    if not isinstance(success, bool):
        raise TypeError(
            "Invalid workflow edit result: success must be bool"
        )

    result: WorkflowEditResult = {"success": success}

    graph = result_value.get("graph")
    if graph is not None:
        if not isinstance(graph, dict):
            raise TypeError(
                "Invalid workflow edit result: graph must be a dictionary"
            )

        result["graph"] = cast(GraphDict, graph)

    error = result_value.get("error")
    if error is not None and not isinstance(error, str):
        raise TypeError(
            "Invalid workflow edit result: error must be string or None"
        )

    result["error"] = error
    return result


def _step(
    params: Params,
    inputs: Inputs,
    state: State,
    dt: float,
) -> tuple[StepResult, State]:
    del dt

    error: str | None = None
    p: Params = params

    current = get_graph_from_inputs(inputs)
    result: GraphDict = dict(current)

    try:
        raw_todo_lists = result.get("todo_lists")

        if raw_todo_lists is not None and not isinstance(raw_todo_lists, list):
            todo_lists: list[JsonValue] | None = None
        else:
            todo_lists = cast(
                list[JsonValue] | None,
                raw_todo_lists,
            )

        raw_batch = p.get("Multiple_edits_sequential")

        if isinstance(raw_batch, list) and raw_batch:
            batch_items = cast(list[object], raw_batch)
            parsed_edits: list[GraphEdit] = []

            for item in batch_items:
                parsed_edits.append(_parse_graph_edit(item))

            batch = MultipleEditsSequential(edits=parsed_edits)

            batch_result = apply_workflow_edits(
                current,
                batch,
                allowed_actions=_ACTIONS,
            )

            if not batch_result.success:
                raise ValueError(
                    batch_result.error
                    or "Batch todo edit failed"
                )

            current = batch_result.graph_after
            result = dict(current)

            todo_lists = cast(
                list[JsonValue] | None,
                result.get("todo_lists"),
            )

        else:
            edit = _parse_graph_edit(_single_edit_params(p))

            todo_lists = _apply_single_edit(
                cast(
                    list[TodoList | JsonValue] | None,
                    todo_lists,
                ),
                edit,
            )

        result["todo_lists"] = todo_lists

    except (TypeError, ValueError) as ex:
        error = str(ex)[:500]

    return (
        {
            "graph": result,
            "error": error,
        },
        state,
    )


def register_todo_list() -> None:
    register_unit(
        UnitSpec(
            type_name="todo_list",
            input_ports=EDIT_INPUT_PORTS,
            output_ports=EDIT_OUTPUT_PORTS,
            step_fn=_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            runtime_scope=None,
            description=(
                "Todo list edit: action=add_todo_list|remove_todo_list|add_task|remove_task|"
                "mark_completed|set_implementer|set_deadline|set_curator; "
                "params: title, text, task_id, completed, todo_list_id, id, implementer, deadline, curator. "
                "Logic in unit: writes into graph key 'todo_lists'. "
                "Supports batch: Multiple_edits_sequential=[{...},{...},...] applied sequentially. "
                "On error, output 'error' contains a message."
            ),
        )
    )


__all__ = ["EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS", "register_todo_list"]
