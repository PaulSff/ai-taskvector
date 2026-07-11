
import logging
import json
import os
from pathlib import Path
from typing import Any

from .prompts import (
    TASK_PREFIX_REVIEW_SOURCE,
    TASK_PREFIX_ADD_CODE_BLOCK,
    TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE,
)


logger = logging.getLogger(__name__)


# ---- Helpers ----

def _default_todo_list_workflow_path() -> Path:
    from agents.tools.workflow_path import get_tool_workflow_path

    return get_tool_workflow_path("todo_manager")


def _ensure_todo_list_if_missing(
    *,
    current: dict[str, Any],
    edits_to_apply: list[dict[str, Any]],
    ensured_todo_list: bool,
    list_id: str,
    title: str,
) -> bool:
    if ensured_todo_list:
        return ensured_todo_list

    todo_lists = current.get("todo_lists")
    if isinstance(todo_lists, list) and todo_lists:
        # ensured if the requested list exists and has a tasks list
        for tl in todo_lists:
            if (
                isinstance(tl, dict)
                and tl.get("id") == list_id
                and isinstance(tl.get("tasks"), list)
            ):
                return True

    edits_to_apply.append(
        {"action": "add_todo_list", "id": list_id, "title": title}
    )
    return True


def _queue_add_task(
    *,
    current: dict[str, Any],
    task_text: str,
    queued_task_texts: set[str],
    edits_to_apply: list[dict[str, Any]],
    list_id: str | None = None,
) -> None:
    text = (task_text or "").strip()
    if not text:
        return
    if text in queued_task_texts:
        return
    # Check against initial graph state (current is not updated mid-queue).
    if _has_open_task_with_text(current, text, list_id=list_id):
        return
    queued_task_texts.add(text)
    edits_to_apply.append({"action": "add_task", "todo_list_id": list_id, "text": text})



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


def _load_tg_history(messages_dir: str) -> list[dict[str, Any]]:
    path = _latest_tg_messages_file(messages_dir)
    if not path:
        logger.debug("TG history not loaded: no latest file for dir=%r", messages_dir)
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            history = [m for m in data if isinstance(m, dict)]
            logger.debug("Loaded TG history: %d items from %s", len(history), path)
            return history

        if isinstance(data, dict):
            by_chat = data.get("messages_by_chat_id")
            if isinstance(by_chat, dict):
                history: list[dict[str, Any]] = []
                for msgs in by_chat.values():
                    if isinstance(msgs, list):
                        history.extend(m for m in msgs if isinstance(m, dict))
                logger.debug(
                    "Loaded TG history: %d items from messages_by_chat_id in %s",
                    len(history),
                    path,
                )
                return history

        logger.debug(
            "TG history JSON was not a list or messages_by_chat_id dict in %s (type=%s)",
            path,
            type(data).__name__,
        )
        return []
    except Exception:
        logger.exception("Failed to load TG history from: %s", path)
        return []


def _extract_message_text(m: dict[str, Any]) -> str:
    try:
        if m.get("content", {}).get("@type") == "messageText":
            text = str((m.get("content", {}).get("text", {}) or {}).get("text") or "")
            logger.debug("Extracted messageText content: %r", text)
            return text
    except Exception:
        logger.exception("Failed extracting messageText content")

    try:
        text = (
            (m.get("content", {}).get("text", {}) or {}).get("text")
            or m.get("text")
            or ""
        )
        result = str(text).strip()
        logger.debug("Extracted fallback message text: %r", result)
        return result
    except Exception:
        logger.exception(
            "Failed extracting fallback message text; returning empty string"
        )
        return ""


def _task_text_reply(chat_id: Any, message_id: Any, text: str) -> str:
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


def _has_open_task_with_text(
    graph: dict[str, Any],
    task_text: str,
    *,
    list_id: str | None = None,
) -> bool:
    if not graph or not isinstance(graph, dict):
        return False
    todo_lists = graph.get("todo_lists")
    if not isinstance(todo_lists, list):
        return False

    want = (task_text or "").strip()
    if not want:
        return False

    for todo in todo_lists:
        if not isinstance(todo, dict):
            continue
        if list_id is not None and todo.get("id") != list_id:
            continue
        tasks = todo.get("tasks")
        if not isinstance(tasks, list):
            continue
        for t in tasks:
            if not isinstance(t, dict) or t.get("completed"):
                continue
            if (t.get("text") or "").strip() == want:
                return True
    return False




def graph_has_any_open_tasks(graph: Any | None) -> bool:
    if graph is None:
        return False
    d = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else graph
    if not isinstance(d, dict):
        return False
    todo_lists = d.get("todo_lists")
    if not isinstance(todo_lists, list):
        return False
    for todo in todo_lists:
        if not isinstance(todo, dict):
            continue
        tasks = todo.get("tasks")
        if not isinstance(tasks, list):
            continue
        for t in tasks:
            if isinstance(t, dict) and not t.get("completed"):
                return True
    return False


def get_unit_ids_with_source_tasks(graph: dict[str, Any] | None) -> list[str]:
    if not graph or not isinstance(graph, dict):
        return []
    todo_lists = graph.get("todo_lists")
    if not isinstance(todo_lists, list):
        return []
    unit_ids: list[str] = []
    for todo in todo_lists:
        if not isinstance(todo, dict):
            continue
        tasks = todo.get("tasks")
        if not isinstance(tasks, list):
            continue
        for t in tasks:
            if not isinstance(t, dict):
                continue
            if t.get("completed"):
                continue
            text = (t.get("text") or "").strip()
            if not text:
                continue
            if text.startswith(TASK_PREFIX_REVIEW_SOURCE):
                uid = text[len(TASK_PREFIX_REVIEW_SOURCE) :].strip()
                if uid:
                    unit_ids.append(uid)
            elif text.startswith(TASK_PREFIX_ADD_CODE_BLOCK):
                uid = text[len(TASK_PREFIX_ADD_CODE_BLOCK) :].strip()
                if uid:
                    unit_ids.append(uid)
    return list(dict.fromkeys(unit_ids))


def get_summary_params(
    coding_is_allowed: bool,
    graph: dict[str, Any] | None,
) -> dict[str, Any]:
    include_code_block_source = bool(coding_is_allowed)
    include_source_for_unit_ids: list[str] | None = None
    if not coding_is_allowed:
        include_source_for_unit_ids = get_unit_ids_with_source_tasks(graph)
    return {
        "include_code_block_source": include_code_block_source,
        "include_source_for_unit_ids": include_source_for_unit_ids or [],
    }


def _as_todo_params_sequential(edits: list[dict[str, Any]]) -> dict[str, Any]:
    if len(edits) == 1:
        return edits[0]
    return {"Multiple_edits_sequential": edits}
