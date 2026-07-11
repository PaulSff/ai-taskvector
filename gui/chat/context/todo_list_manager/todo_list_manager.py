from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Sequence

from gui.components.settings import (
    get_telegram_conversations_dir,
    TG_TODO_LIST_ID,
    GRAPH_TODO_LIST_ID,
    GRAPH_TODO_LIST_TITLE,
)

from .prompts import (
    TASK_PREFIX_REVIEW_SOURCE,
    TASK_PREFIX_ADD_CODE_BLOCK,
    TASK_REVIEW_IMPORTED_WORKFLOW,
    TASK_ENSURE_UNITS_CONNECTED,
    TASK_CHECK_UNITS_PARAMS,
    TASK_ENSURE_DEBUG_FOR_RUN,
    TASK_PREPARE_INITIAL_DATA_FOR_RUN,
    TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE,
)

from .helpers import (
    _default_todo_list_workflow_path,
    _ensure_todo_list_if_missing,
    _queue_add_task,
    _load_tg_history,
    _extract_message_text,
    _task_text_reply,
    _has_open_task_with_text,
    _as_todo_params_sequential,

)

# Telegram conversation history directory
MESSAGES_DIR = get_telegram_conversations_dir()

logger = logging.getLogger(__name__)


# --- Run todo list tool workflow (add tasks, todo-lists, etc. by running the workflow) ---

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


# --- Add todo-lists if not present ---

async def _ensure_todo_list_exists(
    graph: dict[str, Any],
    *,
    list_id: str,
    title: str | None = None,
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    current = graph
    todo_lists = current.get("todo_lists")
    if isinstance(todo_lists, list):
        for tl in todo_lists:
            if (
                isinstance(tl, dict)
                and tl.get("id") == list_id
                and isinstance(tl.get("tasks"), list)
            ):
                return current

    return await _run_todo_list_workflow(
        current,
        {"action": "add_todo_list", "id": list_id, "title": title},
        workflow_path,
    )




# --- Add tasks for read_code_block tool ---

async def add_tasks_for_read_code_block(
    unit_ids: list[str],
    graph: dict[str, Any],
    workflow_path: Path | None = None,
) -> dict[str, Any]:
    if not unit_ids:
        return graph

    current = await _ensure_todo_list_exists(
        graph,
        list_id=GRAPH_TODO_LIST_ID,
        title=GRAPH_TODO_LIST_TITLE,
        workflow_path=workflow_path,
    )


    edits: list[dict[str, Any]] = []
    for uid in unit_ids:
        uid = (uid or "").strip()
        if not uid:
            continue
        task_text = TASK_PREFIX_REVIEW_SOURCE + uid
        if _has_open_task_with_text(current, task_text, list_id=GRAPH_TODO_LIST_ID):
            continue
        edits.append({"action": "add_task", "todo_list_id": str(GRAPH_TODO_LIST_ID), "text": task_text})

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

    current = await _ensure_todo_list_exists(
        graph,
        list_id=GRAPH_TODO_LIST_ID,
        title=GRAPH_TODO_LIST_TITLE,
        workflow_path=workflow_path,
    )


    task_text = TASK_PREFIX_ADD_CODE_BLOCK + unit_id
    if _has_open_task_with_text(current, task_text, list_id=GRAPH_TODO_LIST_ID):
        return current


    return await _run_todo_list_workflow(
        current,
        {"action": "add_task", "todo_list_id": str(GRAPH_TODO_LIST_ID), "text": task_text},
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

    current = await _ensure_todo_list_exists(
        graph,
        list_id=GRAPH_TODO_LIST_ID,
        title=GRAPH_TODO_LIST_TITLE,
        workflow_path=workflow_path,
    )


    edits: list[dict[str, Any]] = []
    if not _has_open_task_with_text(current, text_connected, list_id=GRAPH_TODO_LIST_ID):
        edits.append({"action": "add_task", "todo_list_id": str(GRAPH_TODO_LIST_ID), "text": text_connected})
    if not _has_open_task_with_text(current, text_params, list_id=GRAPH_TODO_LIST_ID):
        edits.append({"action": "add_task", "todo_list_id": str(GRAPH_TODO_LIST_ID), "text": text_params})


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

    current = await _ensure_todo_list_exists(
        graph,
        list_id=GRAPH_TODO_LIST_ID,
        title=GRAPH_TODO_LIST_TITLE,
        workflow_path=workflow_path,
    )


    edits: list[dict[str, Any]] = []
    if not _has_open_task_with_text(current, TASK_ENSURE_DEBUG_FOR_RUN, list_id=GRAPH_TODO_LIST_ID):
        edits.append({"action": "add_task", "todo_list_id": str(GRAPH_TODO_LIST_ID), "text": TASK_ENSURE_DEBUG_FOR_RUN})
    if not _has_open_task_with_text(current, TASK_PREPARE_INITIAL_DATA_FOR_RUN, list_id=GRAPH_TODO_LIST_ID):
        edits.append({"action": "add_task", "todo_list_id": str(GRAPH_TODO_LIST_ID), "text": TASK_PREPARE_INITIAL_DATA_FOR_RUN})


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

    current = await _ensure_todo_list_exists(
        graph,
        list_id=GRAPH_TODO_LIST_ID,
        title=GRAPH_TODO_LIST_TITLE,
        workflow_path=workflow_path,
    )


    if _has_open_task_with_text(current, TASK_REVIEW_IMPORTED_WORKFLOW, list_id=GRAPH_TODO_LIST_ID):
        return current

    return await _run_todo_list_workflow(
        current,
        {"action": "add_task", "todo_list_id": str(GRAPH_TODO_LIST_ID), "text": TASK_REVIEW_IMPORTED_WORKFLOW},
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

    # 3) remove tasks for responded ones, if present (TG list only)
    existing_tasks: list[dict[str, Any]] = []
    todo_lists = current.get("todo_lists")
    if isinstance(todo_lists, list):
        for tl in todo_lists:
            if not isinstance(tl, dict) or tl.get("id") != TG_TODO_LIST_ID:
                continue
            tasks = tl.get("tasks")
            if isinstance(tasks, list):
                existing_tasks.extend([x for x in tasks if isinstance(x, dict)])

    existing_reply_tasks_by_chat: dict[str, list[str]] = {}
    for t in existing_tasks:
        if not isinstance(t, dict) or t.get("completed"):
            continue

        task_id = t.get("id")
        if task_id is None:
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

        # Store task_ids for removal (remove_task expects task_id)
        existing_reply_tasks_by_chat.setdefault(str(chat_id), []).append(str(task_id))

    logger.info(
        "Reply-to detection: existing reply tasks tracked for %d chats",
        len(existing_reply_tasks_by_chat),
    )

    # 2) add tasks for pending, only if no such task on current graph (TG list only)
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
        logger.info("Ensuring todo lists exists for reply-to tasks...")
        await ensure_todo_list_if_missing()

    for task_text in desired_pending_task_texts:
        logger.debug("Queueing reply-to pending task.")
        queue_add_task(task_text)

    for cid in responded_chat_ids:
        existing_task_ids_for_chat = existing_reply_tasks_by_chat.get(cid, [])
        logger.info(
            "Reply-to removals: chat_id=%s matching_existing=%d",
            cid,
            len(existing_task_ids_for_chat),
        )
        for task_id in existing_task_ids_for_chat:
            logger.debug("Queue remove task_id: %r", task_id)
            edits_to_apply.append(
                {
                    "action": "remove_task",
                    "todo_list_id": str(TG_TODO_LIST_ID),
                    "task_id": task_id,
                }
            )

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
            list_id=GRAPH_TODO_LIST_ID,
            title=GRAPH_TODO_LIST_TITLE,
        )

        _queue_add_task(
            current=current,
            task_text=text_connected,
            queued_task_texts=queued_task_texts,
            edits_to_apply=edits_to_apply,
            list_id=GRAPH_TODO_LIST_ID,
        )

        _queue_add_task(
            current=current,
            task_text=text_params,
            queued_task_texts=queued_task_texts,
            edits_to_apply=edits_to_apply,
            list_id=GRAPH_TODO_LIST_ID,
        )


    if any(
        isinstance(e, dict) and e.get("action") == "run_workflow" for e in (edits or [])
    ):
        supplements.append("client: todo tasks for run_workflow (debug + initial data)")
        ensured_todo_list = _ensure_todo_list_if_missing(
            current=current,
            edits_to_apply=edits_to_apply,
            ensured_todo_list=ensured_todo_list,
            list_id=GRAPH_TODO_LIST_ID,
            title=GRAPH_TODO_LIST_TITLE,
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
                list_id=GRAPH_TODO_LIST_ID,
                title=GRAPH_TODO_LIST_TITLE,
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
            list_id=GRAPH_TODO_LIST_ID,
            title=GRAPH_TODO_LIST_TITLE,
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
