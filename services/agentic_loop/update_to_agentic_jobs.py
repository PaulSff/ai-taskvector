"""
Incoming follow-up context update format.

Todo tasks:
{
    "type": "update",
    "update": {
        "tasks_todo": [
            {
                "todo_list_id": "market_research_2026",
                "task": {
                    "id": "task_2bd3bc97",
                    "text": "...",
                    "completed": False,
                    "created_at": "26-08-23-141540",
                    "implementer": None,
                    "curator": None,
                    "finished_at": None,
                    "deadline": "320",
                },
            }
        ]
    },
}

Unread chats:

{
    "type": "update",
    "messenger": "telegram"
    "update": {
        "chats": [...],
    }
}

"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

from pydantic import ValidationError

from core.schemas import TodoTask
from messengers_integrations import MessengerChatUpdate

type AgenticJob = dict[str, object]


def _get_event_payload(
    event: object,
) -> Mapping[str, object] | None:
    """
    The subscriber currently passes the ZMQ payload directly, so this
    normally receives a dict. The `.payload` fallback supports wrapper
    objects if one is introduced later.
    """
    if isinstance(event, Mapping):
        return event

    payload = getattr(event, "payload", None)

    if isinstance(payload, Mapping):
        return payload

    return None


def chat_update_to_agentic_jobs(
    event: object,
) -> list[AgenticJob]:
    """
    Normalize an unread-chat update into agentic jobs.

    Expected payload format:

    {
        "type": "update",
        "messenger": "telegram",
        "update": {
            "chats": [...]
        }
    }
    """
    payload = _get_event_payload(event)

    if payload is None:
        return []

    messenger = payload.get("messenger")

    # The messenger identifies the integration that owns the chat.
    if not isinstance(messenger, str) or not messenger:
        return []

    update = payload.get("update")

    if not isinstance(update, Mapping):
        return []

    chats = update.get("chats")

    if not isinstance(chats, list):
        return []

    jobs: list[AgenticJob] = []

    for raw_chat in chats:
        if not isinstance(raw_chat, Mapping):
            continue

        try:
            chat_update = MessengerChatUpdate.model_validate(raw_chat)
        except ValidationError:
            continue

        if chat_update.unread_count <= 0:
            continue

        if not chat_update.messages:
            continue

        jobs.append(
            {
                "session_id": str(chat_update.chat_id),
                "messenger": messenger,
                "unread_chats": [chat_update],
                "incomplete_tasks": None,
            }
        )

    return jobs


def _normalize_todo_task(task: object) -> TodoTask | None:
    if not isinstance(task, Mapping):
        return None

    try:
        return TodoTask.model_validate(dict(task))
    except ValidationError:
        return None


def todo_update_to_agentic_jobs(
    event: object,
) -> list[AgenticJob]:
    """
    Normalize a todo update into agentic jobs, using `todo_list_id`
    as the session ID.
    """
    payload = _get_event_payload(event)

    if payload is None:
        return []

    update = payload.get("update")

    if not isinstance(update, Mapping):
        return []

    if update.get("error") is not None:
        return []

    tasks_todo = update.get("tasks_todo")

    if not isinstance(tasks_todo, list):
        return []

    incomplete_tasks_by_list: defaultdict[str, list[TodoTask]] = defaultdict(list)

    for task_item in tasks_todo:
        if not isinstance(task_item, Mapping):
            continue

        todo_list_id = task_item.get("todo_list_id")
        raw_task = task_item.get("task")

        if not isinstance(todo_list_id, str) or not todo_list_id:
            continue

        normalized_task = _normalize_todo_task(raw_task)

        if normalized_task is None or normalized_task.completed:
            continue

        incomplete_tasks_by_list[todo_list_id].append(normalized_task)

    return [
        {
            "session_id": todo_list_id,
            "incomplete_tasks": tasks,
        }
        for todo_list_id, tasks in incomplete_tasks_by_list.items()
    ]


def update_to_agentic_jobs(
    event: object,
) -> list[AgenticJob]:
    """
    Dispatch a subscriber payload to the appropriate normalizer.
    """
    payload = _get_event_payload(event)

    if payload is None:
        return []

    update = payload.get("update")

    if not isinstance(update, Mapping):
        return []

    if "tasks_todo" in update:
        return todo_update_to_agentic_jobs(event)

    if "chats" in update:
        return chat_update_to_agentic_jobs(event)

    return []
