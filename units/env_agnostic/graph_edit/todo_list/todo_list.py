"""Todo-list edit: logic in unit, writes todo_list into graph. Params: action, title, text, task_id, completed."""
from __future__ import annotations

from typing import Any

from core.graph.todo_list import (
    add_task as todo_add_task,
    ensure_todo_list as todo_ensure_list,
    mark_completed as todo_mark_completed,
    remove_task as todo_remove_task,
)
from units.registry import UnitSpec, register_unit

EDIT_INPUT_PORTS = [("graph", "Any")]
EDIT_OUTPUT_PORTS = [("graph", "Any")]

_ACTIONS = frozenset({"add_todo_list", "add_task", "remove_task", "remove_todo_list", "mark_completed"})


def _step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    p = params or {}
    action = (p.get("action") or "").strip()
    if action not in _ACTIONS:
        action = "add_todo_list"

    current = inputs.get("graph")
    if current is None:
        current = {}
    result = dict(current)

    todo_list = result.get("todo_list")
    if todo_list is not None and not isinstance(todo_list, dict):
        todo_list = None

    if action == "add_todo_list":
        todo_list = todo_ensure_list(todo_list)
        if p.get("title") is not None and str(p.get("title", "")).strip():
            todo_list = {**todo_list, "title": str(p["title"]).strip()}
    elif action == "remove_todo_list":
        todo_list = None
    elif action == "add_task":
        if not p.get("text") or not str(p.get("text", "")).strip():
            raise ValueError("Incorrect format for add_task: missing required parameter: text (non-empty string)")
        todo_list = todo_ensure_list(todo_list)
        todo_list = todo_add_task(todo_list, str(p["text"]).strip())
    elif action == "remove_task":
        if not p.get("task_id") or not str(p.get("task_id", "")).strip():
            raise ValueError("Incorrect format for remove_task: missing required parameter: task_id")
        todo_list = todo_ensure_list(todo_list)
        todo_list = todo_remove_task(todo_list, str(p["task_id"]).strip())
    elif action == "mark_completed":
        if not p.get("task_id") or not str(p.get("task_id", "")).strip():
            raise ValueError("Incorrect format for mark_completed: missing required parameter: task_id")
        todo_list = todo_ensure_list(todo_list)
        todo_list = todo_mark_completed(
            todo_list, str(p["task_id"]).strip(), completed=p.get("completed", True)
        )

    if todo_list is not None:
        result["todo_list"] = todo_list
    elif "todo_list" in result:
        result["todo_list"] = None

    return ({"graph": result}, state)


def register_todo_list() -> None:
    register_unit(UnitSpec(
        type_name="todo_list",
        input_ports=EDIT_INPUT_PORTS,
        output_ports=EDIT_OUTPUT_PORTS,
        step_fn=_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        runtime_scope=None,
        description="Todo list edit: action=add_todo_list|add_task|remove_task|remove_todo_list|mark_completed; params: title, text, task_id, completed. Logic in unit; writes into graph.",
    ))


__all__ = ["register_todo_list", "EDIT_INPUT_PORTS", "EDIT_OUTPUT_PORTS"]
