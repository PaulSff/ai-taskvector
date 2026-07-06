"""Todo-list edit: logic in unit, writes todo_list into graph. Params: action, title, text, task_id, completed."""

from __future__ import annotations

from typing import Any

from core.graph import apply_workflow_edits
from core.graph.todo_list import (
    add_task as todo_add_task,
)
from core.graph.todo_list import (
    ensure_todo_list as todo_ensure_list,
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


def _apply_single_edit(todo_list: Any, p: dict[str, Any]) -> Any:
    action = (p.get("action") or "").strip()
    if action not in _ACTIONS:
        action = "add_todo_list"

    if action == "add_todo_list":
        todo_list = todo_ensure_list(todo_list)
        if p.get("title") is not None and str(p.get("title", "")).strip():
            todo_list = {**todo_list, "title": str(p["title"]).strip()}
    elif action == "remove_todo_list":
        todo_list = None
    elif action == "add_task":
        if not p.get("text") or not str(p.get("text", "")).strip():
            raise ValueError(
                "Incorrect format for add_task: missing required parameter: text (non-empty string)"
            )
        todo_list = todo_ensure_list(todo_list)
        todo_list = todo_add_task(todo_list, str(p["text"]).strip())
    elif action == "remove_task":
        if not p.get("task_id") or not str(p.get("task_id", "")).strip():
            raise ValueError(
                "Incorrect format for remove_task: missing required parameter: task_id"
            )
        todo_list = todo_ensure_list(todo_list)
        todo_list = todo_remove_task(todo_list, str(p["task_id"]).strip())
    elif action == "mark_completed":
        if not p.get("task_id") or not str(p.get("task_id", "")).strip():
            raise ValueError(
                "Incorrect format for mark_completed: missing required parameter: task_id"
            )
        todo_list = todo_ensure_list(todo_list)
        todo_list = todo_mark_completed(
            todo_list, str(p["task_id"]).strip(), completed=p.get("completed", True)
        )

    return todo_list


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
        todo_list = result.get("todo_list")
        if todo_list is not None and not isinstance(todo_list, dict):
            todo_list = None

        batch = p.get("Multiple_edits_sequential")

        if isinstance(batch, list) and batch:
            batch_result = apply_workflow_edits(
                {"todo_list": todo_list},
                [
                    {
                        "action": (
                            (item or {}).get("action")
                            if isinstance(item, dict)
                            else None
                        ),
                        **(item if isinstance(item, dict) else {}),
                    }
                    for item in batch
                ],
                allowed_actions=_ACTIONS,
            )
            if not batch_result.get("success", False):
                raise ValueError(batch_result.get("error") or "Batch todo edit failed")
            todo_list = batch_result.get("graph", {}).get("todo_list")
        else:
            todo_list = _apply_single_edit(todo_list, p)

        if todo_list is not None:
            result["todo_list"] = todo_list
        elif "todo_list" in result:
            result["todo_list"] = None
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
                "params: title, text, task_id, completed. Logic in unit; writes into graph. "
                "Supports batch: Multiple_edits_sequential=[{...},{...},...] applied sequentially. "
                "On error, output 'error' contains a message."
            ),
        )
    )


__all__ = ["register_todo_list", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
