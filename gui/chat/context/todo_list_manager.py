from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Sequence

from gui.components.settings import get_telegram_conversations_dir

DEFAULT_TODO_LIST_TITLE = "Current flow TODOs"
TASK_PREFIX_REVIEW_SOURCE = "Review the source "
TASK_PREFIX_ADD_CODE_BLOCK = "Add the code block to "

TASK_REVIEW_IMPORTED_WORKFLOW = "Review the workflow"

TASK_ENSURE_UNITS_CONNECTED = "Verify the units connections and ports: {unit_ids}. Ensure the ports types compatibility (e.g. 'tables' -> 'tables') to pass the data in correct format."
TASK_CHECK_UNITS_PARAMS = "Search the units params description on the knowledge base, unless it is a custom function: {unit_ids}. Trace data keys all the way through the flow and adjust the units params to meet the specificaton."
TASK_ENSURE_DEBUG_FOR_RUN = (
    "Ensure to have a Debug unit in place to collect both output Data and Errors from units (typically at the tail of the workflow). "
    "Set a log file path in the Debug unit params to grep the logs from there. "
)
TASK_PREPARE_INITIAL_DATA_FOR_RUN = "Ensure the to have a Template unit with some input data in params for the workflow to test with. Test the workflow, put a comment summarizing the testing result on the graph."

TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE = "Respond to the incoming message: "

# Telegram conversation history directory
MESSAGES_DIR = get_telegram_conversations_dir()

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
) -> bool:
    if ensured_todo_list:
        return ensured_todo_list

    todo = current.get("todo_list")
    if isinstance(todo, dict) and isinstance(todo.get("tasks"), list):
        return True

    edits_to_apply.append({"action": "add_todo_list", "title": DEFAULT_TODO_LIST_TITLE})
    return True


def _queue_add_task(
    *,
    current: dict[str, Any],
    task_text: str,
    queued_task_texts: set[str],
    edits_to_apply: list[dict[str, Any]],
) -> None:
    text = (task_text or "").strip()
    if not text:
        return
    if text in queued_task_texts:
        return
    # Check against initial graph state (current is not updated mid-queue).
    if _has_open_task_with_text(current, text):
        return
    queued_task_texts.add(text)
    edits_to_apply.append({"action": "add_task", "text": text})


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

        logger.debug(
            "TG history JSON was not a list in %s (type=%s)", path, type(data).__name__
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


def _has_open_task_with_text(graph: dict[str, Any], task_text: str) -> bool:
    if not graph or not isinstance(graph, dict):
        return False
    todo = graph.get("todo_list")
    if not isinstance(todo, dict):
        return False
    tasks = todo.get("tasks")
    if not isinstance(tasks, list):
        return False
    want = (task_text or "").strip()
    if not want:
        return False
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
    todo = d.get("todo_list")
    if not isinstance(todo, dict):
        return False
    tasks = todo.get("tasks")
    if not isinstance(tasks, list):
        return False
    for t in tasks:
        if isinstance(t, dict) and not t.get("completed"):
            return True
    return False


def get_unit_ids_with_source_tasks(graph: dict[str, Any] | None) -> list[str]:
    if not graph or not isinstance(graph, dict):
        return []
    todo = graph.get("todo_list")
    if not isinstance(todo, dict):
        return []
    tasks = todo.get("tasks")
    if not isinstance(tasks, list):
        return []
    unit_ids: list[str] = []
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
    # If more than one edit, use the batch input shape; otherwise keep it single-edit.
    if len(edits) == 1:
        return edits[0]
    return {"Multiple_edits_sequential": edits}


# --- Run todo list tool workflow (add tasks, todo-lists, etc. by running the workdlow) ---


def _run_todo_list_workflow_sync(
    graph: dict[str, Any],
    todo_params: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    from runtime.run import run_workflow

    path = workflow_path or _default_todo_list_workflow_path()
    if not path.is_file():
        return graph
    initial_inputs = {"inject_graph": {"data": graph}}
    unit_param_overrides = {"todo_list": todo_params}
    try:
        outputs = run_workflow(
            path,
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format="dict",
        )
        out_graph = (outputs.get("todo_list") or {}).get("graph")
        if isinstance(out_graph, dict):
            return out_graph
    except Exception:
        pass
    return graph


async def _run_todo_list_workflow(
    graph: dict[str, Any],
    todo_params: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _run_todo_list_workflow_sync, graph, todo_params, workflow_path
    )


# --- Add todo-list if not present


async def _ensure_todo_list_exists(
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    current = graph
    todo = current.get("todo_list")
    if not isinstance(todo, dict) or not isinstance(todo.get("tasks"), list):
        current = await _run_todo_list_workflow(
            current,
            {"action": "add_todo_list", "title": DEFAULT_TODO_LIST_TITLE},
            workflow_path,
        )
    return current


# --- Add tasks for read_code_block tool ---


async def add_tasks_for_read_code_block(
    unit_ids: list[str],
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    if not unit_ids:
        return graph

    current = await _ensure_todo_list_exists(graph, workflow_path)

    edits: list[dict[str, Any]] = []
    for uid in unit_ids:
        uid = (uid or "").strip()
        if not uid:
            continue
        task_text = TASK_PREFIX_REVIEW_SOURCE + uid
        if _has_open_task_with_text(current, task_text):
            continue
        edits.append({"action": "add_task", "text": task_text})

    if not edits:
        return current

    return await _run_todo_list_workflow(
        current,
        _as_todo_params_sequential(edits),
        workflow_path,
    )


# --- Add tasks after adding new code blocks into the workflow ---


async def add_task_for_add_code_block(
    unit_id: str,
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    if not (unit_id or "").strip():
        return graph
    unit_id = str(unit_id).strip()

    current = await _ensure_todo_list_exists(graph, workflow_path)

    task_text = TASK_PREFIX_ADD_CODE_BLOCK + unit_id
    if _has_open_task_with_text(current, task_text):
        return current

    return await _run_todo_list_workflow(
        current,
        {"action": "add_task", "text": task_text},
        workflow_path,
    )


# --- Add tasks after adding new units into the workflow ---


async def add_tasks_for_added_units(
    unit_ids: list[str],
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in unit_ids:
        uid = (raw or "").strip()
        if not uid or uid in seen:
            continue
        seen.add(uid)
        ordered.append(uid)
    if not ordered or not graph or not isinstance(graph, dict):
        return graph

    unit_ids_str = ", ".join(ordered)
    text_connected = TASK_ENSURE_UNITS_CONNECTED.format(unit_ids=unit_ids_str)
    text_params = TASK_CHECK_UNITS_PARAMS.format(unit_ids=unit_ids_str)

    current = await _ensure_todo_list_exists(graph, workflow_path)

    edits: list[dict[str, Any]] = []
    if not _has_open_task_with_text(current, text_connected):
        edits.append({"action": "add_task", "text": text_connected})
    if not _has_open_task_with_text(current, text_params):
        edits.append({"action": "add_task", "text": text_params})

    if not edits:
        return current

    return await _run_todo_list_workflow(
        current,
        _as_todo_params_sequential(edits),
        workflow_path,
    )


# --- Add tasks for Run Workflow tool ---


async def add_tasks_for_run_workflow(
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    if not graph or not isinstance(graph, dict):
        return graph

    current = await _ensure_todo_list_exists(graph, workflow_path)

    edits: list[dict[str, Any]] = []
    if not _has_open_task_with_text(current, TASK_ENSURE_DEBUG_FOR_RUN):
        edits.append({"action": "add_task", "text": TASK_ENSURE_DEBUG_FOR_RUN})
    if not _has_open_task_with_text(current, TASK_PREPARE_INITIAL_DATA_FOR_RUN):
        edits.append({"action": "add_task", "text": TASK_PREPARE_INITIAL_DATA_FOR_RUN})

    if not edits:
        return current

    return await _run_todo_list_workflow(
        current,
        _as_todo_params_sequential(edits),
        workflow_path,
    )


# --- Add tasks for Import Workflow tool ---


async def add_review_workflow_task_after_import(
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    if not graph or not isinstance(graph, dict):
        return graph

    current = await _ensure_todo_list_exists(graph, workflow_path)

    if _has_open_task_with_text(current, TASK_REVIEW_IMPORTED_WORKFLOW):
        return current

    return await _run_todo_list_workflow(
        current,
        {"action": "add_task", "text": TASK_REVIEW_IMPORTED_WORKFLOW},
        workflow_path,
    )


# --- Add tasks for unhandled Tg messages ---

async def add_tasks_for_unhandled_tg_messages(
    *,
    current: dict[str, Any],
    edits_to_apply: list[dict[str, Any]],
    ensure_todo_list_if_missing,
    queue_add_task,
    workflow_path: Path | None = None,
) -> Any:
    try:
        messages_dir = MESSAGES_DIR  # must exist in your module scope
    except Exception:
        messages_dir = None

    if not messages_dir:
        logger.info("No MESSAGES_DIR; skipping unhandled tg messages tasks.")
        return None

    logger.info(
        "Processing incoming message reply-to tracking (dir=%r)...",
        messages_dir,
    )
    history = _load_tg_history(str(messages_dir))
    logger.info("TG history loaded for reply-to tracking: %d items", len(history))

    # 1) detect last message per chat_id
    by_chat: dict[str, dict[str, Any]] = {}
    for m in history:
        if not isinstance(m, dict):
            continue
        chat_id = m.get("chat_id")
        if chat_id is None:
            continue
        cid = str(chat_id)
        prev = by_chat.get(cid)
        if prev is None:
            by_chat[cid] = m
        else:
            prev_date = prev.get("date") or 0
            cur_date = m.get("date") or 0
            if cur_date >= prev_date:
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

    logger.info(
        "Reply-to detection: pending_chat_ids=%d responded_chat_ids=%d",
        len(pending_chat_ids),
        len(responded_chat_ids),
    )

    # 3) remove tasks for responded ones, if present
    existing_tasks: list[dict[str, Any]] = []
    todo = current.get("todo_list")
    if isinstance(todo, dict):
        tasks = todo.get("tasks")
        if isinstance(tasks, list):
            existing_tasks = [x for x in tasks if isinstance(x, dict)]

    existing_reply_tasks_by_chat: dict[str, list[str]] = {}
    for t in existing_tasks:
        if not isinstance(t, dict) or t.get("completed"):
            continue
        text = (t.get("text") or "").strip()
        if not text.startswith(TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE):
            continue
        payload_str = text[len(TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE) :].strip()
        try:
            payload = json.loads(payload_str) if payload_str else {}
        except Exception:
            logger.debug("Skipping task with invalid reply-to payload text=%r", text)
            continue
        chat_id = payload.get("chat_id")
        if chat_id is None:
            continue
        existing_reply_tasks_by_chat.setdefault(str(chat_id), []).append(text)

    logger.info(
        "Reply-to detection: existing reply tasks tracked for %d chats",
        len(existing_reply_tasks_by_chat),
    )

    # 2) add tasks for pending, only if no such task on current graph
    desired_pending_task_texts: set[str] = set()
    for cid in pending_chat_ids:
        last_msg = by_chat.get(cid)
        if not last_msg:
            continue
        chat_id = last_msg.get("chat_id")
        message_id = last_msg.get("id")
        if chat_id is None or message_id is None:
            continue
        text = _extract_message_text(last_msg)
        desired_pending_task_texts.add(
            _task_text_reply(str(chat_id), message_id, text)
        )

    logger.info(
        "Reply-to tasks to add: %d pending; removals chats: %d",
        len(desired_pending_task_texts),
        len(responded_chat_ids),
    )

    start_len = len(edits_to_apply)

    # Batch add/remove like augment_graph_with_client_tasks
    if desired_pending_task_texts or responded_chat_ids:
        logger.info("Ensuring todo list exists for reply-to tasks...")
        ensure_todo_list_if_missing()

    for task_text in desired_pending_task_texts:
        logger.debug("Queueing reply-to pending task.")
        queue_add_task(task_text)

    for cid in responded_chat_ids:
        existing_for_chat = existing_reply_tasks_by_chat.get(cid, [])
        logger.info(
            "Reply-to removals: chat_id=%s matching_existing=%d",
            cid,
            len(existing_for_chat),
        )
        for existing_text in existing_for_chat:
            logger.debug("Queue remove task: %r", existing_text)
            edits_to_apply.append({"action": "remove_task", "text": existing_text})

    batch_edits = edits_to_apply[start_len:]
    if not batch_edits:
        return None

    if len(batch_edits) == 1:
        todo_params = batch_edits[0]
    else:
        todo_params = {"Multiple_edits_sequential": batch_edits}

    return await _run_todo_list_workflow(current, todo_params, workflow_path)



# --- Add a bunch of tasks at Workflow Designer follow-up rounds ---


async def augment_graph_with_client_tasks(
    graph: dict[str, Any],
    edits: Sequence[Any] | None,
    *,
    coding_is_allowed: bool,
    workflow_path: Path | None = None,
) -> tuple[dict[str, Any], list[str]]:
    supplements: list[str] = []
    if not graph or not isinstance(graph, dict):
        return graph, supplements

    current = graph

    edits_to_apply: list[dict[str, Any]] = []
    ensured_todo_list = False
    queued_task_texts: set[str] = set()

    # Collect added unit ids
    added_unit_ids: list[str] = []
    for e in edits or []:
        if isinstance(e, dict) and e.get("action") == "add_unit":
            u = e.get("unit") or {}
            uid = (u.get("id") or "").strip()
            if uid:
                added_unit_ids.append(uid)

    if added_unit_ids:
        supplements.append("client: todo tasks for add_unit (connections + params)")

    ordered_unit_ids: list[str] = []
    seen_uids: set[str] = set()
    for raw in added_unit_ids:
        uid = (raw or "").strip()
        if uid and uid not in seen_uids:
            seen_uids.add(uid)
            ordered_unit_ids.append(uid)

    if ordered_unit_ids:
        unit_ids_str = ", ".join(ordered_unit_ids)
        text_connected = TASK_ENSURE_UNITS_CONNECTED.format(unit_ids=unit_ids_str)
        text_params = TASK_CHECK_UNITS_PARAMS.format(unit_ids=unit_ids_str)

        ensured_todo_list = _ensure_todo_list_if_missing(
            current=current,
            edits_to_apply=edits_to_apply,
            ensured_todo_list=ensured_todo_list,
        )
        _queue_add_task(
            current=current,
            task_text=text_connected,
            queued_task_texts=queued_task_texts,
            edits_to_apply=edits_to_apply,
        )
        _queue_add_task(
            current=current,
            task_text=text_params,
            queued_task_texts=queued_task_texts,
            edits_to_apply=edits_to_apply,
        )

    if any(
        isinstance(e, dict) and e.get("action") == "run_workflow" for e in (edits or [])
    ):
        supplements.append("client: todo tasks for run_workflow (debug + initial data)")
        ensured_todo_list = _ensure_todo_list_if_missing(
            current=current,
            edits_to_apply=edits_to_apply,
            ensured_todo_list=ensured_todo_list,
        )
        _queue_add_task(
            current=current,
            task_text=TASK_ENSURE_DEBUG_FOR_RUN,
            queued_task_texts=queued_task_texts,
            edits_to_apply=edits_to_apply,
        )
        _queue_add_task(
            current=current,
            task_text=TASK_PREPARE_INITIAL_DATA_FOR_RUN,
            queued_task_texts=queued_task_texts,
            edits_to_apply=edits_to_apply,
        )

    if coding_is_allowed:
        code_unit_ids: list[str] = []
        for e in edits or []:
            if isinstance(e, dict) and e.get("action") == "add_unit":
                u = e.get("unit") or {}
                if str(u.get("type", "")).strip().lower() in ("function", "script"):
                    uid = (u.get("id") or "").strip()
                    if uid:
                        code_unit_ids.append(uid)

        for uid in list(dict.fromkeys(code_unit_ids)):
            ensured_todo_list = _ensure_todo_list_if_missing(
                current=current,
                edits_to_apply=edits_to_apply,
                ensured_todo_list=ensured_todo_list,
            )
            _queue_add_task(
                current=current,
                task_text=TASK_PREFIX_ADD_CODE_BLOCK + uid,
                queued_task_texts=queued_task_texts,
                edits_to_apply=edits_to_apply,
            )

        if code_unit_ids:
            supplements.append("client: todo task for code block unit")

    if any(
        isinstance(e, dict) and e.get("action") == "import_workflow"
        for e in (edits or [])
    ):
        supplements.append('client: todo task "Review the workflow"')
        ensured_todo_list = _ensure_todo_list_if_missing(
            current=current,
            edits_to_apply=edits_to_apply,
            ensured_todo_list=ensured_todo_list,
        )
        _queue_add_task(
            current=current,
            task_text=TASK_REVIEW_IMPORTED_WORKFLOW,
            queued_task_texts=queued_task_texts,
            edits_to_apply=edits_to_apply,
        )

    if not edits_to_apply:
        return current, supplements

    if len(edits_to_apply) == 1:
        todo_params = edits_to_apply[0]
    else:
        todo_params = {"Multiple_edits_sequential": edits_to_apply}

    updated = await _run_todo_list_workflow(current, todo_params, workflow_path)
    return updated, supplements
