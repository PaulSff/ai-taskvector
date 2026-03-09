"""
Todo list logic for graph metadata. Operates on dict: todo_list = { "id", "title?", "tasks": [ { "id", "text", "completed", "created_at" } ] }.
Used by core.graph.graph_edits (apply) and by units.env_agnostic.graph_edit.todo_list (unit).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def default_todo_list_dict(list_id: str = "todo_list_default", title: str | None = None) -> dict[str, Any]:
    """Return a new todo list dict with no tasks."""
    out: dict[str, Any] = {"id": list_id, "tasks": []}
    if title is not None and str(title).strip():
        out["title"] = str(title).strip()
    return out


def ensure_todo_list(todo_list: dict[str, Any] | None) -> dict[str, Any]:
    """Return the existing todo_list dict or a new default. Does not mutate input."""
    if todo_list is not None and isinstance(todo_list, dict) and isinstance(todo_list.get("tasks"), list):
        return dict(todo_list)
    return default_todo_list_dict()


def add_task(
    todo_list: dict[str, Any],
    text: str,
    task_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Add a task to the list. Returns a new dict; does not mutate input."""
    text = str(text).strip()
    if not text:
        raise ValueError("Task text cannot be empty")
    task_id = task_id or ("task_" + uuid4().hex[:8])
    created_at = created_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tasks = list(todo_list.get("tasks") or [])
    for t in tasks:
        if isinstance(t, dict) and t.get("id") == task_id:
            raise ValueError(f"Task id already exists: {task_id}")
    tasks.append({
        "id": task_id,
        "text": text,
        "completed": False,
        "created_at": created_at,
    })
    out = dict(todo_list)
    out["tasks"] = tasks
    return out


def remove_task(todo_list: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Remove a task by id. Returns a new dict; does not mutate input."""
    task_id = str(task_id).strip()
    if not task_id:
        raise ValueError("Task id is required")
    tasks = [t for t in (todo_list.get("tasks") or []) if isinstance(t, dict) and t.get("id") != task_id]
    if len(tasks) == len(todo_list.get("tasks") or []):
        raise ValueError(f"Task not found: {task_id}")
    out = dict(todo_list)
    out["tasks"] = tasks
    return out


def mark_completed(todo_list: dict[str, Any], task_id: str, completed: bool = True) -> dict[str, Any]:
    """Set a task's completed flag. Returns a new dict; does not mutate input."""
    task_id = str(task_id).strip()
    if not task_id:
        raise ValueError("Task id is required")
    tasks_old = todo_list.get("tasks") or []
    tasks: list[dict[str, Any]] = []
    found = False
    for t in tasks_old:
        if not isinstance(t, dict):
            continue
        if t.get("id") == task_id:
            tasks.append({**t, "completed": bool(completed)})
            found = True
        else:
            tasks.append(dict(t))
    if not found:
        raise ValueError(f"Task not found: {task_id}")
    out = dict(todo_list)
    out["tasks"] = tasks
    return out
