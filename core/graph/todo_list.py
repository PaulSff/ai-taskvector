from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


# --- helpers ---

def _clean_optional_str(x: Any) -> str | None:
    if x is None:
        return None
    s = str(x).strip()
    return s if s else None

# ---------------

def default_todo_list_dict(
    list_id: str = "todo_list_default",
    title: str | None = "Current TODOs",
) -> dict[str, Any]:
    """Return a new todo list dict with no tasks."""
    out: dict[str, Any] = {"id": list_id, "tasks": []}

    if title is not None:
        t = str(title).strip()
        out["title"] = t if t else None
    return out


def ensure_todo_lists(todo_lists: Any) -> list[dict[str, Any]]:
    """Return existing todo_lists as a list[dict]. Does not mutate input."""
    if todo_lists is None:
        return []

    if isinstance(todo_lists, list) and all(isinstance(x, dict) for x in todo_lists):
        return [dict(x) for x in todo_lists]

    return []


def create_new_todo_list(
    todo_lists: Any,
    *,
    title: str | None = None,
    list_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    "Add a new todo list on top of the existing one": create a fresh list and prepend it (index 0).
    Returns updated todo_lists (does not mutate input).
    """
    tl = ensure_todo_lists(todo_lists)
    new_id = list_id or ("todo_list_" + uuid4().hex[:8])
    new_list = default_todo_list_dict(list_id=new_id, title=title)
    return [new_list, *tl]


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
    created_at = created_at or datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    tasks = list(todo_list.get("tasks") or [])
    for t in tasks:
        if isinstance(t, dict) and t.get("id") == task_id:
            raise ValueError(f"Task id already exists: {task_id}")
    tasks.append(
        {
            "id": task_id,
            "text": text,
            "completed": False,
            "created_at": created_at,
        }
    )
    out = dict(todo_list)
    out["tasks"] = tasks
    return out


def remove_task(todo_list: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Remove a task by id. Returns a new dict; does not mutate input."""
    task_id = str(task_id).strip()
    if not task_id:
        raise ValueError("Task id is required")
    tasks = [
        t
        for t in (todo_list.get("tasks") or [])
        if isinstance(t, dict) and t.get("id") != task_id
    ]
    if len(tasks) == len(todo_list.get("tasks") or []):
        raise ValueError(f"Task not found: {task_id}")
    out = dict(todo_list)
    out["tasks"] = tasks
    return out


def mark_completed(
    todo_list: dict[str, Any],
    task_id: str,
    completed: bool = True,
) -> dict[str, Any]:
    """Set a task's completed flag and optionally set finished_at. Returns a new dict; does not mutate input."""
    task_id = str(task_id).strip()
    if not task_id:
        raise ValueError("Task id is required")

    finished_at = (
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if completed else None
    )

    tasks_old = todo_list.get("tasks") or []
    tasks: list[dict[str, Any]] = []
    found = False

    for t in tasks_old:
        if not isinstance(t, dict):
            continue
        if t.get("id") == task_id:
            updated = {**t, "completed": bool(completed)}
            if completed:
                updated["finished_at"] = finished_at
            else:
                updated["finished_at"] = t.get("finished_at") if t.get("finished_at") is not None else None
            tasks.append(updated)
            found = True
        else:
            tasks.append(dict(t))

    if not found:
        raise ValueError(f"Task not found: {task_id}")

    out = dict(todo_list)
    out["tasks"] = tasks
    return out


def set_implementer(
    todo_list: dict[str, Any],
    task_id: str,
    implementer: str | None,
) -> dict[str, Any]:
    """Set task implementer. Returns a new dict; does not mutate input."""
    task_id = str(task_id).strip()
    if not task_id:
        raise ValueError("Task id is required")

    implementer = _clean_optional_str(implementer)

    tasks_old = todo_list.get("tasks") or []
    tasks: list[dict[str, Any]] = []
    found = False

    for t in tasks_old:
        if not isinstance(t, dict):
            continue
        if t.get("id") == task_id:
            updated = dict(t)
            if implementer is None:
                updated.pop("implementer", None)
            else:
                updated["implementer"] = implementer
            tasks.append(updated)
            found = True
        else:
            tasks.append(dict(t))

    if not found:
        raise ValueError(f"Task not found: {task_id}")

    out = dict(todo_list)
    out["tasks"] = tasks
    return out


def set_deadline(
    todo_list: dict[str, Any],
    task_id: str,
    deadline: str | None,
) -> dict[str, Any]:
    """Set task deadline. Returns a new dict; does not mutate input."""
    task_id = str(task_id).strip()
    if not task_id:
        raise ValueError("Task id is required")

    deadline = _clean_optional_str(deadline)

    tasks_old = todo_list.get("tasks") or []
    tasks: list[dict[str, Any]] = []
    found = False

    for t in tasks_old:
        if not isinstance(t, dict):
            continue
        if t.get("id") == task_id:
            updated = dict(t)
            if deadline is None:
                updated.pop("deadline", None)
            else:
                updated["deadline"] = deadline
            tasks.append(updated)
            found = True
        else:
            tasks.append(dict(t))

    if not found:
        raise ValueError(f"Task not found: {task_id}")

    out = dict(todo_list)
    out["tasks"] = tasks
    return out


def set_curator(
    todo_list: dict[str, Any],
    task_id: str,
    curator: str | None,
) -> dict[str, Any]:
    """Set task curator. Returns a new dict; does not mutate input."""
    task_id = str(task_id).strip()
    if not task_id:
        raise ValueError("Task id is required")

    curator = _clean_optional_str(curator)

    tasks_old = todo_list.get("tasks") or []
    tasks: list[dict[str, Any]] = []
    found = False

    for t in tasks_old:
        if not isinstance(t, dict):
            continue
        if t.get("id") == task_id:
            updated = dict(t)
            if curator is None:
                updated.pop("curator", None)
            else:
                updated["curator"] = curator
            tasks.append(updated)
            found = True
        else:
            tasks.append(dict(t))

    if not found:
        raise ValueError(f"Task not found: {task_id}")

    out = dict(todo_list)
    out["tasks"] = tasks
    return out
