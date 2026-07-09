"""Todo-list edit: logic in unit, writes todo_lists into graph. Params: action, title, text, task_id, completed, todo_list_id, id."""

from __future__ import annotations

from typing import Any

from core.graph import apply_workflow_edits
from core.graph.todo_list import (
    add_task as todo_add_task,
)
from core.graph.todo_list import (
    ensure_todo_lists as todo_ensure_lists,
)
from core.graph.todo_list import (
    create_new_todo_list as todo_create_new_list,
)
from core.graph.todo_list import (
    mark_completed as todo_mark_completed,
)
from core.graph.todo_list import (
    remove_task as todo_remove_task,
)
from units.canonical.graph_edit._apply import get_graph_from_inputs
from units.registry import UnitSpec, register_unit

EDIT_INPUT_PORTS = [("data", "Any"), ("graph", "Any")]
EDIT_OUTPUT_PORTS = [("graph", "Any"), ("error", "Any")]

_ACTIONS = frozenset(
    {"add_todo_list", "add_task", "remove_task", "remove_todo_list", "mark_completed"}
)


def _apply_single_edit(todo_lists: Any, p: dict[str, Any]) -> Any:
    action = (p.get("action") or "").strip()
    if action not in _ACTIONS:
        action = "add_todo_list"

    todo_lists = todo_ensure_lists(todo_lists)

    if action == "add_todo_list":
        # Optional: id (or list_id), optional title
        provided_id = p.get("id", None)
        if provided_id is None:
            provided_id = p.get("list_id", None)

        list_id = None
        if provided_id is not None:
            s = str(provided_id).strip()
            list_id = s if s else None

        title = p.get("title", None)
        return todo_create_new_list(
            todo_lists,
            title=title,
            list_id=list_id,
        )

    if action == "remove_todo_list":
        if not p.get("id") or not str(p.get("id", "")).strip():
            raise ValueError("Incorrect format for remove_todo_list: missing required parameter: id")

        target_id = str(p["id"]).strip()
        filtered_lists = [tl for tl in todo_lists if str(tl.get("id")) != target_id]
        if len(filtered_lists) == len(todo_lists):
            raise ValueError(f"Todo list not found: {target_id}")
        return filtered_lists

    if action in {"add_task", "remove_task", "mark_completed"}:
        if not todo_lists:
            raise ValueError("No todo lists exist")

        # Choose target list
        if len(todo_lists) == 1:
            target_list_id = str(todo_lists[0].get("id"))
        else:
            if not p.get("todo_list_id") or not str(p.get("todo_list_id", "")).strip():
                raise ValueError(
                    f"Incorrect format for {action}: missing required parameter: todo_list_id (todo list id)"
                )
            target_list_id = str(p["todo_list_id"]).strip()

        # Apply within target list
        new_lists = []
        task_added = False
        task_removed = False
        task_found = False

        if action == "add_task":
            if not p.get("text") or not str(p.get("text", "")).strip():
                raise ValueError(
                    "Incorrect format for add_task: missing required parameter: text (non-empty string)"
                )
            task_text = str(p["text"]).strip()

            for tl in todo_lists:
                if str(tl.get("id")) == target_list_id:
                    new_lists.append(todo_add_task(tl, task_text))
                    task_added = True
                else:
                    new_lists.append(dict(tl))

            if not task_added:
                raise ValueError(f"Todo list not found: {target_list_id}")
            return new_lists

        if action == "remove_task":
            if not p.get("task_id") or not str(p.get("task_id", "")).strip():
                raise ValueError(
                    "Incorrect format for remove_task: missing required parameter: task_id"
                )
            task_id = str(p["task_id"]).strip()

            for tl in todo_lists:
                if str(tl.get("id")) == target_list_id:
                    try:
                        new_lists.append(todo_remove_task(tl, task_id))
                        task_removed = True
                    except ValueError:
                        new_lists.append(dict(tl))
                else:
                    new_lists.append(dict(tl))

            if not task_removed:
                raise ValueError(f"Task not found: {task_id}")
            return new_lists

        # mark_completed
        if not p.get("task_id") or not str(p.get("task_id", "")).strip():
            raise ValueError(
                "Incorrect format for mark_completed: missing required parameter: task_id"
            )
        task_id = str(p["task_id"]).strip()
        completed = p.get("completed", True)

        for tl in todo_lists:
            if str(tl.get("id")) == target_list_id:
                try:
                    new_lists.append(todo_mark_completed(tl, task_id, completed=completed))
                    task_found = True
                except ValueError:
                    new_lists.append(dict(tl))
            else:
                new_lists.append(dict(tl))

        if not task_found:
            raise ValueError(f"Task not found: {task_id}")
        return new_lists

    return todo_lists


def _step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    p = params or {}
    error: Any = None

    current = get_graph_from_inputs(inputs)
    result = dict(current)

    try:
        todo_lists = result.get("todo_lists")
        if todo_lists is not None and not isinstance(todo_lists, list):
            todo_lists = None

        batch = p.get("Multiple_edits_sequential")

        if isinstance(batch, list) and batch:
            batch_result = apply_workflow_edits(
                {"todo_lists": todo_lists},
                [
                    {
                        "action": ((item or {}).get("action") if isinstance(item, dict) else None),
                        **(item if isinstance(item, dict) else {}),
                    }
                    for item in batch
                ],
                allowed_actions=_ACTIONS,
            )
            if not batch_result.get("success", False):
                raise ValueError(batch_result.get("error") or "Batch todo edit failed")
            todo_lists = batch_result.get("graph", {}).get("todo_lists")
        else:
            todo_lists = _apply_single_edit(todo_lists, p)

        result["todo_lists"] = todo_lists if todo_lists is not None else None
    except Exception as ex:
        error = str(ex)[:500]

    return ({"graph": result, "error": error}, state)


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
                "Todo list edit: action=add_todo_list|add_task|remove_task|remove_todo_list|mark_completed; "
                "params: title, text, task_id, completed, todo_list_id, id. "
                "Logic in unit: writes into graph key 'todo_lists'. "
                "Supports batch: Multiple_edits_sequential=[{...},{...},...] applied sequentially. "
                "On error, output 'error' contains a message."
            ),
        )
    )


__all__ = ["register_todo_list", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
