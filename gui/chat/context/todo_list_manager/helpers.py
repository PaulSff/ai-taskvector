
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
from messengers_integrations.telegram.telegram_bot_api.helpers import (
    get_blacklist_file,
    load_conf_yaml,
    default_conf,
)

logger = logging.getLogger(__name__)

# Telegram Bot config
conf = load_conf_yaml(os.environ.get("CONF_YAML_PATH", default_conf))


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
    if isinstance(todo_lists, list):
        for tl in todo_lists:
            if isinstance(tl, dict) and str(tl.get("id")) == str(list_id):
                # If the list exists, don't add it again.
                # If tasks is missing/not a list, your workflow can fix it later,
                # or you can add an "init tasks" edit here if you have such an action.
                if not isinstance(tl.get("tasks"), list):
                    tl["tasks"] = []
                return True

    edits_to_apply.append({"action": "add_todo_list", "id": list_id, "title": title})
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


def _queue_remove_task(
    *,
    edits_to_apply: list[dict[str, Any]],
    todo_list_id: str,
    task_id: str | int | None,
) -> None:
    if task_id is None:
        return
    edits_to_apply.append(
        {
            "action": "remove_task",
            "todo_list_id": str(todo_list_id),
            "task_id": str(task_id),
        }
    )


def queue_set_deadline_for_task(
    *,
    edits_to_apply: list[dict[str, Any]],
    task_id: str,
    deadline: int | float | None,
    TG_TODO_LIST_ID: str,
) -> None:
    edits_to_apply.append(
        {
            "action": "set_deadline",
            "task_id": str(task_id),
            "deadline": str(deadline) if deadline is not None else None,  # optional_nonempty_or_null_string
            "todo_list_id": str(TG_TODO_LIST_ID),
        }
    )


def _reply_key_from_task_text(task_text: str) -> tuple[str, str] | None:
    text = (task_text or "").strip()
    if not text.startswith(TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE):
        return None
    payload_str = text[len(TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE) :].strip()
    try:
        payload = json.loads(payload_str) if payload_str else {}
    except Exception:
        return None
    chat_id = payload.get("chat_id")
    message_id = payload.get("message_id")
    if chat_id is None or message_id is None:
        return None
    return (str(chat_id), str(message_id))


def _dedupe_graph_tasks_and_lists(
    graph: dict[str, Any],
    *,
    todo_list_id: str,
) -> dict[str, Any]:
    g = graph or {}
    todo_lists = g.get("todo_lists")
    if not isinstance(todo_lists, list):
        return g

    # Dedupe todo_lists by id (merge tasks for same todo_list_id)
    by_id: dict[str, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for tl in todo_lists:
        if not isinstance(tl, dict):
            continue
        tl_id = tl.get("id")
        if tl_id is None:
            continue
        tl_id = str(tl_id)
        if tl_id not in by_id:
            by_id[tl_id] = tl
            out.append(tl)
        else:
            if tl_id == str(todo_list_id):
                a = by_id[tl_id].setdefault("tasks", [])
                b = tl.get("tasks")
                if isinstance(a, list) and isinstance(b, list):
                    a.extend([x for x in b if isinstance(x, dict)])

    g["todo_lists"] = out

    # Dedupe tasks inside TG list by reply key (only for open tasks)
    for tl in g.get("todo_lists", []):
        if not isinstance(tl, dict) or str(tl.get("id")) != str(todo_list_id):
            continue
        tasks = tl.get("tasks")
        if not isinstance(tasks, list):
            continue

        seen_keys: set[tuple[str, str]] = set()
        new_tasks: list[dict[str, Any]] = []

        for t in tasks:
            if not isinstance(t, dict):
                continue

            if t.get("completed"):
                new_tasks.append(t)
                continue

            key = _reply_key_from_task_text((t.get("text") or "").strip())
            if key is None:
                new_tasks.append(t)
                continue

            if key in seen_keys:
                continue
            seen_keys.add(key)
            new_tasks.append(t)

        tl["tasks"] = new_tasks

    return g



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


def _load_tg_black_list(messages_dir: str) -> dict[str, dict[str, Any]]:
    path = _tg_black_list_path(messages_dir)
    if not path:
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            logger.debug(
                "tg_black_list file was not a dict in %s (type=%s)",
                path,
                type(data).__name__,
            )
            return {}

        # New schema: { "<bot_id>": { "<chat_id>": <epoch_s>, ... }, ... }
        normalized: dict[str, dict[str, Any]] = {}
        for bot_id, chat_map in data.items():
            if not isinstance(bot_id, str):
                bot_id = str(bot_id)

            if not isinstance(chat_map, dict):
                continue

            inner: dict[str, Any] = {}
            for chat_id, epoch_s in chat_map.items():
                if chat_id is None:
                    continue
                inner[str(chat_id)] = epoch_s

            if inner:
                normalized[bot_id] = inner

        logger.debug(
            "Loaded TG blacklist (new schema): %d bot ids from %s",
            len(normalized),
            path,
        )
        return normalized
    except Exception:
        logger.exception("Failed to load TG blacklist from: %s", path)
        return {}


def classify_replyto_chats_from_history(
    history: list[dict[str, Any]],
    blacklisted_chat_ids: set[str],
) -> tuple[set[str], set[str]]:
    """
    Classify chats from Telegram message history into “pending” (last message was sent by the chat) vs “responded” (last message was sent by someone else), excluding any chats present in `blacklisted_chat_ids`.

        Returns:
            (pending_chat_ids, responded_chat_ids)
    """
    def _safe_int(x: Any) -> int | None:
        try:
            return int(x)
        except Exception:
            return None

    # 1) detect last message per chat_id by greatest message "id"
    by_chat: dict[str, dict[str, Any]] = {}
    for m in history:
        if not isinstance(m, dict):
            continue
        chat_id = m.get("chat_id")
        msg_id = m.get("id")
        if chat_id is None or msg_id is None:
            continue

        cid = str(chat_id)
        prev = by_chat.get(cid)

        if prev is None:
            by_chat[cid] = m
            continue

        prev_msg_id = prev.get("id")
        msg_i = _safe_int(msg_id)
        prev_i = _safe_int(prev_msg_id)

        # Avoid crashing on non-numeric ids; if either isn't numeric, keep prev.
        if msg_i is None or prev_i is None:
            continue

        if msg_i >= prev_i:
            by_chat[cid] = m

    pending_chat_ids: set[str] = set()
    responded_chat_ids: set[str] = set()

    for cid, last_msg in by_chat.items():
        from_id = (last_msg.get("from") or {}).get("id")
        if from_id is None:
            continue
        if str(from_id) == cid:
            pending_chat_ids.add(cid)
        else:
            responded_chat_ids.add(cid)

    if blacklisted_chat_ids:
        pending_chat_ids = {cid for cid in pending_chat_ids if cid not in blacklisted_chat_ids}

    return pending_chat_ids, responded_chat_ids


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
