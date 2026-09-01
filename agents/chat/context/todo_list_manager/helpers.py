
import json
import logging
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TypeGuard, cast

from core.normalizer.shared import as_object_dict
from core.schemas import ProcessGraph, TodoList, TodoTask
from core.schemas.graph_edit_api import GraphEdit, MultipleEditsSequential
from core.schemas.primitives import JsonObject, JsonValue, safe_int
from messengers_integrations.messenger_state import HistoryMessage
from messengers_integrations.telegram.telegram_bot_api.helpers import (
    default_conf,
    get_blacklist_file,
    load_conf_yaml,
)

from .prompts import (
    TASK_PREFIX_ADD_CODE_BLOCK,
    TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE,
    TASK_PREFIX_REVIEW_SOURCE,
)
from .todo_state import IncompleteTaskResult

logger = logging.getLogger(__name__)

# Telegram Bot config
conf = load_conf_yaml(os.environ.get("CONF_YAML_PATH", default_conf))

# ---- Helpers ----

def default_todo_list_workflow_path() -> Path:
    from agents.tools.workflow_path import get_tool_workflow_path

    return get_tool_workflow_path("todo_manager")


def ensure_todo_list_if_missing(
    *,
    current: ProcessGraph,
    edits_to_apply: list[GraphEdit],
    ensured_todo_list: bool,
    list_id: str,
    title: str,
) -> None:
    if ensured_todo_list:
        return

    for todo_list in current.todo_lists:
        if todo_list.id == list_id:
            return

    edits_to_apply.append(
        GraphEdit(
            action="add_todo_list",
            id=list_id,
            title=title,
        )
    )


def queue_add_task(
    *,
    current: ProcessGraph,
    task_text: str,
    queued_task_texts: set[str],
    edits_to_apply: list[GraphEdit],
    list_id: str | None = None,
) -> None:
    text = task_text.strip()

    if not text:
        return

    if text in queued_task_texts:
        return

    # Check against the initial graph state.
    # `current` is not updated while edits are being queued.
    if has_open_task_with_text(
        current,
        text,
        list_id=list_id,
    ):
        return

    queued_task_texts.add(text)

    edits_to_apply.append(
        GraphEdit(
            action="add_task",
            todo_list_id=list_id or "",
            text=text,
        )
    )


def queue_remove_task(
    *,
    edits_to_apply: list[GraphEdit],
    todo_list_id: str,
    task_id: str | int | None,
) -> None:
    if task_id is None:
        return

    edits_to_apply.append(
        GraphEdit(
            action="remove_task",
            todo_list_id=todo_list_id,
            task_id=str(task_id),
        )
    )



def queue_set_deadline_for_task(
    *,
    edits_to_apply: list[GraphEdit],
    task_id: str,
    deadline: float | None,
    TG_TODO_LIST_ID: str,
) -> None:
    edits_to_apply.append(
        GraphEdit(
            action="set_deadline",
            task_id=str(task_id),
            deadline=str(deadline) if deadline is not None else None,
            todo_list_id=str(TG_TODO_LIST_ID),
        )
    )



def reply_key_from_task_text(task_text: str) -> tuple[str, str] | None:
    text = (task_text or "").strip()
    if not text.startswith(TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE):
        return None

    payload_str = text[len(TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE) :].strip()
    try:
        payload: dict[str, object] = json.loads(payload_str) if payload_str else {}
    except json.JSONDecodeError:
        return None

    chat_id = payload.get("chat_id")
    message_id = payload.get("message_id")
    if chat_id is None or message_id is None:
        return None
    return (str(chat_id), str(message_id))


def dedupe_graph_tasks_and_lists(
    graph: ProcessGraph,
    *,
    todo_list_id: str,
) -> ProcessGraph:
    todo_lists = graph.todo_lists

    # Dedupe todo lists by ID.
    by_id: dict[str, TodoList] = {}
    out: list[TodoList] = []

    for todo_list in todo_lists:
        tl_id = str(todo_list.id)

        if tl_id not in by_id:
            by_id[tl_id] = todo_list
            out.append(todo_list)
        elif tl_id == str(todo_list_id):
            by_id[tl_id].tasks.extend(todo_list.tasks)

    graph.todo_lists = out

    # Dedupe tasks inside the target list by reply key.
    for todo_list in graph.todo_lists:
        if str(todo_list.id) != str(todo_list_id):
            continue

        seen_keys: set[tuple[str, str]] = set()
        new_tasks: list[TodoTask] = []

        for task in todo_list.tasks:
            if task.completed:
                new_tasks.append(task)
                continue

            key = reply_key_from_task_text(task.text.strip())
            if key is None:
                new_tasks.append(task)
                continue

            if key in seen_keys:
                continue

            seen_keys.add(key)
            new_tasks.append(task)

        todo_list.tasks = new_tasks

    return graph



def _latest_tg_messages_file(messages_dir: str) -> str | None:
    try:
        if not messages_dir or not os.path.isdir(messages_dir):
            logger.debug("TG messages dir missing/invalid: %r", messages_dir)
            return None

        candidates = [
            os.path.join(messages_dir, f)
            for f in os.listdir(messages_dir)
            if f.startswith("tg_messages") and f.endswith(".json")
        ]
        if not candidates:
            logger.debug("No tg_messages*.json found in: %r", messages_dir)
            return None

        latest = max(candidates, key=lambda p: os.path.getmtime(p))
        logger.debug("Latest TG messages file selected: %s", latest)
        return latest
    except Exception:
        logger.exception(
            "Failed to select latest TG messages file from: %r", messages_dir
        )
        return None


def _is_message_dict(value: object) -> TypeGuard[HistoryMessage]:
    if not isinstance(value, dict):
        return False

    candidate = cast(dict[object, object], value)

    return all(isinstance(key, str) for key in candidate)


def load_tg_history(messages_dir: str) -> list[HistoryMessage]:
    path = _latest_tg_messages_file(messages_dir)

    if not path:
        logger.debug(
            "TG history not loaded: no latest file for dir=%r",
            messages_dir,
        )
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = cast(object, json.load(f))

        if isinstance(data, list):
            messages = cast(list[object], data)

            list_history: list[HistoryMessage] = [
                message
                for message in messages
                if _is_message_dict(message)
            ]

            logger.debug(
                "Loaded TG history: %d items from %s",
                len(list_history),
                path,
            )
            return list_history

        if isinstance(data, dict):
            data_dict = cast(dict[object, object], data)
            by_chat = data_dict.get("messages_by_chat_id")

            if isinstance(by_chat, dict):
                by_chat_dict = cast(dict[object, object], by_chat)
                grouped_history: list[HistoryMessage] = []

                for raw_messages in by_chat_dict.values():
                    if not isinstance(raw_messages, list):
                        continue

                    messages = cast(list[object], raw_messages)

                    grouped_history.extend(
                        message
                        for message in messages
                        if _is_message_dict(message)
                    )

                logger.debug(
                    "Loaded TG history: %d items from "
                    + "messages_by_chat_id in %s",
                    len(grouped_history),
                    path,
                )
                return grouped_history

        logger.debug(
            "TG history JSON was not a list or "
            + "messages_by_chat_id dict in %s (type=%s)",
            path,
            type(cast(object, data)).__name__,
        )
        return []

    except (OSError, json.JSONDecodeError):
        logger.exception(
            "Failed to load TG history from: %s",
            path,
        )
        return []


def extract_message_text(m: HistoryMessage) -> str:
    content = as_object_dict(m.get("content"))

    if content is not None and content.get("@type") == "messageText":
        text_data = as_object_dict(content.get("text"))

        text = ""
        if text_data is not None:
            text = str(text_data.get("text") or "")

        logger.debug("Extracted messageText content: %r", text)
        return text

    text = ""

    if content is not None:
        text_data = as_object_dict(content.get("text"))
        if text_data is not None:
            text = str(text_data.get("text") or "")

    if not text:
        text = str(m.get("text") or "")

    result = text.strip()
    logger.debug("Extracted fallback message text: %r", result)
    return result


def task_text_reply(chat_id: str, message_id: str, text: str) -> str:
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    task = TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE + json.dumps(
        payload, ensure_ascii=False
    )
    logger.debug(
        "Built reply-to task text: chat_id=%r message_id=%r text_len=%d",
        chat_id,
        message_id,
        len(text or ""),
    )
    return task

def _tg_black_list_path(messages_dir: str) -> str | None:
    try:
        if not messages_dir or not os.path.isdir(messages_dir):
            logger.debug("TG messages dir missing/invalid: %r", messages_dir)
            return None

        p = os.path.join(messages_dir, get_blacklist_file(conf))
        if not os.path.exists(p):
            logger.debug("tg_black_list file not found in: %r", messages_dir)
            return None

        return p
    except Exception:
        logger.exception("Failed to build tg_black_list path from: %r", messages_dir)
        return None


def load_tg_black_list(
    messages_dir: str,
) -> dict[str, dict[str, object]]:
    path = _tg_black_list_path(messages_dir)
    if not path:
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = cast(object, json.load(f))

        if not isinstance(data, dict):
            logger.debug(
                "tg_black_list file was not a dict in %s (type=%s)",
                path,
                type(data).__name__,
            )
            return {}

        raw_data = cast(dict[object, object], data)

        # Schema:
        # {"<bot_id>": {"<chat_id>": <epoch_s>, ...}, ...}
        normalized: dict[str, dict[str, object]] = {}

        for raw_bot_id, raw_chat_map in raw_data.items():
            bot_id = str(raw_bot_id)

            if not isinstance(raw_chat_map, dict):
                continue

            chat_map = cast(dict[object, object], raw_chat_map)
            inner: dict[str, object] = {}

            for raw_chat_id, epoch_s in chat_map.items():
                if raw_chat_id is None:
                    continue

                inner[str(raw_chat_id)] = epoch_s

            if inner:
                normalized[bot_id] = inner

        logger.debug(
            "Loaded TG blacklist (new schema): %d bot ids from %s",
            len(normalized),
            path,
        )
        return normalized

    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to load TG blacklist from: %s", path)
        return {}


def classify_replyto_chats_from_history(
    *,
    history: list[HistoryMessage],
    blacklisted_chat_ids: set[str],
) -> tuple[set[str], set[str]]:
    """
    Classify chats into pending and responded based on their latest message.
    Blacklisted chat IDs are excluded.
    """

    by_chat: dict[str, HistoryMessage] = {}

    for message in history:
        chat_id = message.get("chat_id")
        msg_id = message.get("id")

        if chat_id is None or msg_id is None:
            continue

        chat_id_str = str(chat_id)
        previous = by_chat.get(chat_id_str)

        if previous is None:
            by_chat[chat_id_str] = message
            continue

        current_id = safe_int(msg_id)
        previous_id = safe_int(previous.get("id"))

        # If either ID is not numeric, retain the existing message.
        if current_id is None or previous_id is None:
            continue

        if current_id >= previous_id:
            by_chat[chat_id_str] = message

    pending_chat_ids: set[str] = set()
    responded_chat_ids: set[str] = set()

    for chat_id, last_message in by_chat.items():
        raw_from = last_message.get("from")

        if not isinstance(raw_from, dict):
            continue

        from_data = cast(dict[object, object], raw_from)
        from_id = from_data.get("id")

        if from_id is None:
            continue

        if str(from_id) == chat_id:
            pending_chat_ids.add(chat_id)
        else:
            responded_chat_ids.add(chat_id)

    pending_chat_ids.difference_update(blacklisted_chat_ids)
    responded_chat_ids.difference_update(blacklisted_chat_ids)

    return pending_chat_ids, responded_chat_ids



def has_open_task_with_text(
    graph: ProcessGraph,
    task_text: str,
    *,
    list_id: str | None = None,
) -> bool:
    want = task_text.strip()
    if not want:
        return False

    for todo_list in graph.todo_lists:
        if list_id is not None and str(todo_list.id) != list_id:
            continue

        for task in todo_list.tasks:
            if task.completed:
                continue

            if task.text.strip() == want:
                return True

    return False


def graph_has_any_open_tasks(graph: ProcessGraph | None) -> bool:
    if graph is None:
        return False

    for todo_list in graph.todo_lists:
        for task in todo_list.tasks:
            if not task.completed:
                return True

    return False


def get_unit_ids_with_source_tasks(graph: ProcessGraph | None) -> list[str]:
    if graph is None:
        return []

    unit_ids: list[str] = []

    for todo_list in graph.todo_lists:
        for task in todo_list.tasks:
            if task.completed:
                continue

            text = task.text.strip()
            if not text:
                continue

            if text.startswith(TASK_PREFIX_REVIEW_SOURCE):
                unit_id = text[len(TASK_PREFIX_REVIEW_SOURCE):].strip()
            elif text.startswith(TASK_PREFIX_ADD_CODE_BLOCK):
                unit_id = text[len(TASK_PREFIX_ADD_CODE_BLOCK):].strip()
            else:
                continue

            if unit_id:
                unit_ids.append(unit_id)

    return list(dict.fromkeys(unit_ids))


def get_summary_params(
    coding_is_allowed: bool,
    graph: ProcessGraph | None,
) -> JsonObject:
    include_code_block_source = bool(coding_is_allowed)
    include_source_for_unit_ids: list[JsonValue] = []

    if not coding_is_allowed:
        include_source_for_unit_ids.extend(
            get_unit_ids_with_source_tasks(graph)
        )

    return {
        "include_code_block_source": include_code_block_source,
        "include_source_for_unit_ids": include_source_for_unit_ids,
    }


def as_todo_params_sequential(
    edits: list[GraphEdit],
) -> MultipleEditsSequential:
    return MultipleEditsSequential(
        edits=edits,
    )


def has_action(edit: object, action: str) -> bool:
    if isinstance(edit, GraphEdit):
        return edit.action == action

    if not isinstance(edit, Mapping):
        return False

    edit_mapping = cast(Mapping[str, object], edit)
    value = edit_mapping.get("action")

    return isinstance(value, str) and value == action



def get_added_unit(edit: object) -> Mapping[str, object] | None:
    if not isinstance(edit, Mapping):
        return None

    edit_mapping = cast(Mapping[str, object], edit)

    if edit_mapping.get("action") != "add_unit":
        return None

    raw_unit = edit_mapping.get("unit")
    if not isinstance(raw_unit, Mapping):
        return None

    unit = cast(Mapping[str, object], raw_unit)
    return unit


def get_incomplete_tasks(
    *,
    current: ProcessGraph,
    task_matches: Callable[[TodoTask], bool] | None = None,
) -> list[IncompleteTaskResult]:
    """
    Return incomplete tasks across all todo lists.
    """
    tasks_incomplete: list[IncompleteTaskResult] = []

    for todo_list in current.todo_lists:
        todo_list_id = str(todo_list.id)

        for task in todo_list.tasks:
            if task.completed:
                continue

            if task_matches is not None and not task_matches(task):
                continue

            tasks_incomplete.append(
                {
                    "todo_list_id": todo_list_id,
                    "task": task,
                }
            )

    return tasks_incomplete
