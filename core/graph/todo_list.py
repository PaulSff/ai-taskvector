from __future__ import annotations

import datetime
from collections.abc import Sequence
from typing import cast
from uuid import uuid4

from core.schemas import TodoList, TodoTask
from core.schemas.primitives import JsonValue


def default_todo_list_dict(
    list_id: str = "todo_list_default",
    title: str | None = "Current TODOs",
) -> dict[str, object]:
    """Return a new todo list dict with no tasks."""
    out: dict[str, object] = {"id": list_id, "tasks": []}

    if title is not None:
        t = str(title).strip()
        out["title"] = t if t else None
    return out


def ensure_todo_lists(todo_lists: list[TodoList] | None) -> list[TodoList]:
    """Return a shallow copy of the todo lists without mutating the input."""
    return list(todo_lists) if todo_lists is not None else []


def create_new_todo_list(
    todo_lists: list[TodoList],
    *,
    title: str | None = None,
    list_id: str | None = None,
) -> list[TodoList]:
    new_list = TodoList(
        id=list_id or f"todo_list_{uuid4().hex[:8]}",
        title=title.strip() if title and title.strip() else None,
    )
    return [new_list, *todo_lists]


def add_task(
    todo_list: TodoList,
    text: str,
    task_id: str | None = None,
    created_at: str | None = None,
) -> TodoList:
    text = text.strip()
    if not text:
        raise ValueError("Task text cannot be empty")

    task_id = task_id or f"task_{uuid4().hex[:8]}"

    if any(task.id == task_id for task in todo_list.tasks):
        raise ValueError(f"Task id already exists: {task_id}")

    task = TodoTask(
        id=task_id,
        text=text,
        created_at=(
            created_at
            or datetime.datetime.now(datetime.UTC).isoformat()
        ),
    )

    return todo_list.model_copy(
        update={"tasks": [*todo_list.tasks, task]}
    )


def remove_task(todo_list: TodoList, task_id: str) -> TodoList:
    task_id = task_id.strip()
    if not task_id:
        raise ValueError("Task id is required")

    tasks = [task for task in todo_list.tasks if task.id != task_id]

    if len(tasks) == len(todo_list.tasks):
        raise ValueError(f"Task not found: {task_id}")

    return todo_list.model_copy(update={"tasks": tasks})


def mark_completed(
    todo_list: TodoList,
    task_id: str,
    completed: bool = True,
) -> TodoList:
    task_id = task_id.strip()
    if not task_id:
        raise ValueError("Task id is required")

    finished_at = (
        datetime.datetime.now(datetime.UTC).isoformat()
        if completed
        else None
    )

    found = False
    tasks: list[TodoTask] = []

    for task in todo_list.tasks:
        if task.id != task_id:
            tasks.append(task)
            continue

        found = True
        tasks.append(
            task.model_copy(
                update={
                    "completed": completed,
                    "finished_at": finished_at,
                }
            )
        )

    if not found:
        raise ValueError(f"Task not found: {task_id}")

    return todo_list.model_copy(update={"tasks": tasks})


def set_implementer(
    todo_list: TodoList,
    task_id: str,
    implementer: str | None,
) -> TodoList:
    implementer = implementer.strip() if implementer else None

    tasks = [
        task.model_copy(update={"implementer": implementer})
        if task.id == task_id
        else task
        for task in todo_list.tasks
    ]

    if all(task.id != task_id for task in todo_list.tasks):
        raise ValueError(f"Task not found: {task_id}")

    return todo_list.model_copy(update={"tasks": tasks})



def set_deadline(
    todo_list: TodoList,
    task_id: str,
    deadline: str | None,
) -> TodoList:
    """Set a task deadline without mutating the input TodoList."""
    task_id = task_id.strip()
    if not task_id:
        raise ValueError("Task id is required")

    deadline = deadline.strip() if deadline else None

    found = False
    tasks: list[TodoTask] = []

    for task in todo_list.tasks:
        if task.id == task_id:
            found = True
            tasks.append(
                task.model_copy(
                    update={"deadline": deadline}
                )
            )
        else:
            tasks.append(task)

    if not found:
        raise ValueError(f"Task not found: {task_id}")

    return todo_list.model_copy(update={"tasks": tasks})


def set_curator(
    todo_list: TodoList,
    task_id: str,
    curator: str | None,
) -> TodoList:
    """Set a task's curator without mutating the input TodoList."""
    task_id = task_id.strip()
    if not task_id:
        raise ValueError("Task id is required")

    curator = curator.strip() if curator else None

    found = False
    tasks: list[TodoTask] = []

    for task in todo_list.tasks:
        if task.id == task_id:
            found = True
            tasks.append(
                task.model_copy(
                    update={"curator": curator}
                )
            )
        else:
            tasks.append(task)

    if not found:
        raise ValueError(f"Task not found: {task_id}")

    return todo_list.model_copy(update={"tasks": tasks})


def set_todo_list_title(
    todo_list: TodoList,
    title: str | None,
) -> TodoList:
    title = title.strip() if title else None
    return todo_list.model_copy(update={"title": title})


# ---- helpers ---
def _todo_task_to_dict(
    task: TodoTask | JsonValue,
) -> dict[str, JsonValue] | None:
    if isinstance(task, TodoTask):
        result = task.model_dump(mode="json", by_alias=True)
        return result

    if isinstance(task, dict):
        return dict(task)

    return None


def todo_list_to_dict(
    todo_list: TodoList | JsonValue,
) -> dict[str, JsonValue] | None:
    """Ensure todo_list is a plain dict with ``tasks`` as plain dictionaries."""
    if isinstance(todo_list, TodoList):
        todo_list_dict = todo_list.model_dump(mode="json", by_alias=True)
    elif isinstance(todo_list, dict):
        todo_list_dict = dict(todo_list)
    else:
        return None

    raw_tasks = todo_list_dict.get("tasks")
    if not isinstance(raw_tasks, list):
        return todo_list_dict

    tasks = cast(list[JsonValue], raw_tasks)
    out_tasks: list[JsonValue] = []

    for task in tasks:
        task_dict = _todo_task_to_dict(task)
        if task_dict is not None:
            out_tasks.append(task_dict)

    todo_list_dict["tasks"] = out_tasks
    return todo_list_dict


def todo_lists_to_list(
    todo_lists: Sequence[TodoList | JsonValue] | None,
) -> list[JsonValue]:
    """Normalize ProcessGraph.todo_lists into a JSON-compatible list."""
    if todo_lists is None:
        return []

    out: list[JsonValue] = []

    for todo_list in todo_lists:
        todo_list_dict = todo_list_to_dict(todo_list)
        if todo_list_dict is not None:
            out.append(todo_list_dict)

    return out

def normalize_tasks(value: object) -> list[TodoTask]:
    if value is None:
        return []

    if not isinstance(value, list):
        raise TypeError("tasks must be a list")

    normalized: list[TodoTask] = []

    for item in cast(list[object], value):
        if isinstance(item, TodoTask):
            normalized.append(item)
            continue

        if not isinstance(item, dict):
            raise TypeError(f"Invalid task value: {item!r}")

        task_data = cast(dict[str, object], item)

        try:
            normalized.append(TodoTask.model_validate(task_data))
        except Exception as exc:
            raise ValueError(f"Invalid task: {task_data!r}") from exc

    return normalized


def normalize_todo_lists(value: object) -> list[TodoList]:
    if value is None:
        return []

    if not isinstance(value, list):
        raise TypeError("todo_lists must be a list")

    try:
        return [
            item
            if isinstance(item, TodoList)
            else TodoList.model_validate(cast(dict[str, object], item))
            for item in cast(list[object], value)
        ]
    except Exception as exc:
        raise ValueError("Invalid todo_lists value") from exc
