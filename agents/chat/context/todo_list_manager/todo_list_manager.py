from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from core.normalizer.shared import to_json_value
from core.schemas import ProcessGraph, TodoTask
from core.schemas.primitives import WorkflowInputs, safe_int
from gui.components.settings import (
    GRAPH_TODO_LIST_ID,
    GRAPH_TODO_LIST_TITLE,
    TG_TODO_LIST_ID,
    TG_TODO_LIST_TITLE,
    get_telegram_conversations_dir,
)
from messengers_integrations.messenger_state import HistoryMessage

from .helpers import (
    as_todo_params_sequential,
    classify_replyto_chats_from_history,
    dedupe_graph_tasks_and_lists,
    default_todo_list_workflow_path,
    ensure_todo_list_if_missing,
    extract_message_text,
    get_added_unit,
    has_action,
    has_open_task_with_text,
    load_tg_black_list,
    load_tg_history,
    queue_add_task,
    queue_remove_task,
    queue_set_deadline_for_task,
    reply_key_from_task_text,
    task_text_reply,
)
from .prompts import (
    TASK_CHECK_UNITS_PARAMS,
    TASK_ENSURE_DEBUG_FOR_RUN,
    TASK_ENSURE_UNITS_CONNECTED,
    TASK_PREFIX_ADD_CODE_BLOCK,
    TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE,
    TASK_PREFIX_REVIEW_SOURCE,
    TASK_PREPARE_INITIAL_DATA_FOR_RUN,
    TASK_REVIEW_IMPORTED_WORKFLOW,
)
from .todo_state import (
    AddTaskEdit,
    AddTodoListEdit,
    EnsureTodoListIfMissing,
    MultipleEditsSequential,
    QueueAddTask,
    ReplyToIncomingMessagePayload,
    TodoEdit,
    TodoParams,
    todo_params_to_workflow_inputs,
)

# Telegram conversation history directory
MESSAGES_DIR = get_telegram_conversations_dir()

logger = logging.getLogger("TodoListManager")

# --- Run todo list tool workflow (add tasks, todo-lists, etc. by running the workflow) ---

def _run_todo_list_workflow_sync(
    graph: ProcessGraph,
    todo_params: TodoParams,
    workflow_path: Path | None = None,
) -> ProcessGraph:
    from runtime.run import run_workflow

    path = workflow_path or default_todo_list_workflow_path()
    if not path.is_file():
        return graph

    initial_inputs: WorkflowInputs = {
            "inject_graph": {
                "data": to_json_value(graph.model_dump(mode="json")),
            }
        }
    # convert TodoParams to WorkflowInputs before passing to run_workflow
    unit_param_overrides = todo_params_to_workflow_inputs(todo_params)

    try:
        outputs = run_workflow(
            path,
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format="dict",
        )
    except (OSError, ValueError) as exc:
        logger.warning("Todo workflow failed for %s: %s", path, exc)
        return graph

    todo_output = outputs.get("todo_list")
    if not isinstance(todo_output, dict):
        return graph

    out_graph = todo_output.get("graph")
    if isinstance(out_graph, ProcessGraph):
        return out_graph

    return graph


async def _run_todo_list_workflow(
    graph: ProcessGraph,
    todo_params: TodoParams,
    workflow_path: Path | None = None,
) -> ProcessGraph:
    return await asyncio.to_thread(
        _run_todo_list_workflow_sync, graph, todo_params, workflow_path
    )


# --- Add todo-lists if not present ---

async def _ensure_todo_list_exists(
    graph: ProcessGraph,
    *,
    list_id: str,
    title: str | None = None,
    workflow_path: Path | None = None,
) -> ProcessGraph:
    current = graph

    for todo_list in current.todo_lists:
        if todo_list.id == list_id:
            return current

    add_list_edit: AddTodoListEdit = {
        "action": "add_todo_list",
        "id": list_id,
        "title": title or "",
    }

    return await _run_todo_list_workflow(
        current,
        add_list_edit,
        workflow_path,
    )


# --- Add tasks for read_code_block tool ---

async def add_tasks_for_read_code_block(
    unit_ids: list[str],
    graph: ProcessGraph,
    workflow_path: Path | None = None,
) -> ProcessGraph:
    if not unit_ids:
        return graph

    current = await _ensure_todo_list_exists(
        graph,
        list_id=GRAPH_TODO_LIST_ID,
        title=GRAPH_TODO_LIST_TITLE,
        workflow_path=workflow_path,
    )

    edits: list[TodoEdit] = []
    seen_unit_ids: set[str] = set()

    for raw_uid in unit_ids:
        uid = (raw_uid or "").strip()

        if not uid or uid in seen_unit_ids:
            continue

        seen_unit_ids.add(uid)
        task_text = TASK_PREFIX_REVIEW_SOURCE + uid

        if has_open_task_with_text(
            current,
            task_text,
            list_id=GRAPH_TODO_LIST_ID,
        ):
            continue

        edit: AddTaskEdit = {
            "action": "add_task",
            "todo_list_id": GRAPH_TODO_LIST_ID,
            "text": task_text,
        }
        edits.append(edit)

    if not edits:
        return current

    todo_params: MultipleEditsSequential = {
        "Multiple_edits_sequential": edits,
    }

    return await _run_todo_list_workflow(
        current,
        todo_params,
        workflow_path,
    )

# --- Add tasks after adding new code blocks into the workflow ---

async def add_task_for_add_code_block(
    unit_id: str,
    graph: ProcessGraph,
    workflow_path: Path | None = None,
) -> ProcessGraph:
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
    if has_open_task_with_text(current, task_text, list_id=GRAPH_TODO_LIST_ID):
        return current


    return await _run_todo_list_workflow(
        current,
        {"action": "add_task", "todo_list_id": str(GRAPH_TODO_LIST_ID), "text": task_text},
        workflow_path,
    )


# --- Add tasks after adding new units into the workflow ---

async def add_tasks_for_added_units(
    unit_ids: list[str],
    graph: ProcessGraph,
    workflow_path: Path | None = None,
) -> ProcessGraph:
    ordered: list[str] = []
    seen: set[str] = set()

    for raw in unit_ids:
        uid = (raw or "").strip()
        if not uid or uid in seen:
            continue

        seen.add(uid)
        ordered.append(uid)

    if not ordered:
        return graph

    unit_ids_str = ", ".join(ordered)
    text_connected = TASK_ENSURE_UNITS_CONNECTED.format(
        unit_ids=unit_ids_str
    )
    text_params = TASK_CHECK_UNITS_PARAMS.format(
        unit_ids=unit_ids_str
    )

    current = await _ensure_todo_list_exists(
        graph,
        list_id=GRAPH_TODO_LIST_ID,
        title=GRAPH_TODO_LIST_TITLE,
        workflow_path=workflow_path,
    )

    edits: list[TodoEdit] = []

    if not has_open_task_with_text(
        current,
        text_connected,
        list_id=GRAPH_TODO_LIST_ID,
    ):
        connected_edit: AddTaskEdit = {
            "action": "add_task",
            "todo_list_id": GRAPH_TODO_LIST_ID,
            "text": text_connected,
        }
        edits.append(connected_edit)

    if not has_open_task_with_text(
        current,
        text_params,
        list_id=GRAPH_TODO_LIST_ID,
    ):
        params_edit: AddTaskEdit = {
            "action": "add_task",
            "todo_list_id": GRAPH_TODO_LIST_ID,
            "text": text_params,
        }
        edits.append(params_edit)

    if not edits:
        return current

    return await _run_todo_list_workflow(
        current,
        as_todo_params_sequential(edits),
        workflow_path,
    )


# --- Add tasks for Run Workflow tool ---

async def add_tasks_for_run_workflow(
    graph: ProcessGraph,
    workflow_path: Path | None = None,
) -> ProcessGraph:
    current = await _ensure_todo_list_exists(
        graph,
        list_id=GRAPH_TODO_LIST_ID,
        title=GRAPH_TODO_LIST_TITLE,
        workflow_path=workflow_path,
    )

    edits: list[TodoEdit] = []

    if not has_open_task_with_text(
        current,
        TASK_ENSURE_DEBUG_FOR_RUN,
        list_id=GRAPH_TODO_LIST_ID,
    ):
        debug_edit: AddTaskEdit = {
            "action": "add_task",
            "todo_list_id": GRAPH_TODO_LIST_ID,
            "text": TASK_ENSURE_DEBUG_FOR_RUN,
        }
        edits.append(debug_edit)

    if not has_open_task_with_text(
        current,
        TASK_PREPARE_INITIAL_DATA_FOR_RUN,
        list_id=GRAPH_TODO_LIST_ID,
    ):
        initial_data_edit: AddTaskEdit = {
            "action": "add_task",
            "todo_list_id": GRAPH_TODO_LIST_ID,
            "text": TASK_PREPARE_INITIAL_DATA_FOR_RUN,
        }
        edits.append(initial_data_edit)

    if not edits:
        return current

    return await _run_todo_list_workflow(
        current,
        as_todo_params_sequential(edits),
        workflow_path,
    )


# --- Add tasks for Import Workflow tool ---

async def add_review_workflow_task_after_import(
    graph: ProcessGraph,
    workflow_path: Path | None = None,
) -> ProcessGraph:
    if not graph or not isinstance(graph, dict):
        return graph

    current = await _ensure_todo_list_exists(
        graph,
        list_id=GRAPH_TODO_LIST_ID,
        title=GRAPH_TODO_LIST_TITLE,
        workflow_path=workflow_path,
    )


    if has_open_task_with_text(current, TASK_REVIEW_IMPORTED_WORKFLOW, list_id=GRAPH_TODO_LIST_ID):
        return current

    return await _run_todo_list_workflow(
        current,
        {"action": "add_task", "todo_list_id": str(GRAPH_TODO_LIST_ID), "text": TASK_REVIEW_IMPORTED_WORKFLOW},
        workflow_path,
    )


# ---- Add tasks for Telegram unhandled messages

async def add_tasks_for_unhandled_tg_messages(
    *,
    current: ProcessGraph,
    edits_to_apply: list[TodoEdit],
    ensure_todo_list_if_missing: EnsureTodoListIfMissing,
    queue_add_task: QueueAddTask,
    workflow_path: Path | None = None,
    deadline: float | None = None,
) -> ProcessGraph | None:

    try:
        messages_dir = MESSAGES_DIR
    except NameError:
        messages_dir = None

    if not messages_dir:
        logger.info("Todo_list_manager: No MESSAGES_DIR; skipping unhandled tg messages tasks.")
        return None

    logger.info("Todo_list_manager: Processing incoming message reply-to tracking (dir=%r)...", messages_dir)
    history: list[HistoryMessage] = load_tg_history(str(messages_dir))
    logger.info("Todo_list_manager: TG history loaded for reply-to tracking: %d items", len(history))

    # --- Blacklist loading (reply-to tasks; ignore epoch) ---
    all_bl = load_tg_black_list(str(messages_dir))
    blacklisted_chat_ids: set[str] = set()

    # all_bl: { "<bot_token>": { "<chat_id>": <blocked_epoch_s>, ... }, ... }
    for chat_map in all_bl.values():
        for chat_id in chat_map:
            blacklisted_chat_ids.add(str(chat_id))


    logger.info(
        "Todo_list_manager: blacklist filtering (all bots): blacklisted_chat_ids=%d",
        len(blacklisted_chat_ids),
    )

    # -----------------------------------------

    pending_chat_ids, responded_chat_ids = classify_replyto_chats_from_history(
        history=history,
        blacklisted_chat_ids=blacklisted_chat_ids,
    )

    logger.info(
        "Todo_list_manager: Reply-to detection: pending_chat_ids=%d responded_chat_ids=%d",
        len(pending_chat_ids),
        len(responded_chat_ids),
    )

    # 3) Gather existing TG todo tasks from current
    existing_tasks: list[TodoTask] = []

    for todo_list in current.todo_lists:
        if todo_list.id != str(TG_TODO_LIST_ID):
            continue

        existing_tasks.extend(todo_list.tasks)


    # removals happen in separate batch
    edits_remove_batch: list[TodoEdit] = []

    # Always remove all open blacklisted reply-to tasks.
    did_blacklist_removals = False

    if blacklisted_chat_ids:
        for task in existing_tasks:
            if task.completed:
                continue

            text = task.text.strip()
            if not text.startswith(TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE):
                continue

            payload_str = text[len(TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE):].strip()

            try:
                payload = ReplyToIncomingMessagePayload.model_validate_json(
                    payload_str or "{}"
                )
            except (TypeError, ValueError, ValidationError):
                continue

            chat_id = str(payload.chat_id)
            if chat_id not in blacklisted_chat_ids:
                continue

            queue_remove_task(
                edits_to_apply=edits_remove_batch,
                todo_list_id=str(TG_TODO_LIST_ID),
                task_id=task.id,
            )
            did_blacklist_removals = True

            logger.info(
                "Todo_list_manager: Queuing blacklist removal: chat_id=%s task_id=%r",
                chat_id,
                task.id,
            )

    # Capture which open reply-to tasks already exist from the current graph.
    existing_reply_tasks_by_chat: dict[str, list[str]] = {}
    existing_open_reply_keys: set[tuple[str, str]] = set()

    for task in existing_tasks:
        if task.completed:
            continue

        text = task.text.strip()
        if not text.startswith(TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE):
            continue

        key = reply_key_from_task_text(text)
        if key is not None:
            existing_open_reply_keys.add(key)

        payload_str = text[len(TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE):].strip()

        try:
            payload = ReplyToIncomingMessagePayload.model_validate_json(
                payload_str or "{}"
            )
        except (TypeError, ValueError, ValidationError):
            logger.debug(
                "Todo_list_manager: Skipping task with invalid reply-to payload text=%r",
                text,
            )
            continue

        chat_id = str(payload.chat_id)
        existing_reply_tasks_by_chat.setdefault(chat_id, []).append(task.id)

    logger.info(
        "Todo_list_manager: Reply-to detection: existing reply tasks tracked for %d chats",
        len(existing_reply_tasks_by_chat),
    )

    # 2) Add tasks for pending chats, but only if no matching open task exists.
    desired_pending_task_texts: set[str] = set()
    desired_pending_reply_keys: set[tuple[str, str]] = set()

    # Rebuild the latest message per chat for pending-task creation.
    by_chat: dict[str, HistoryMessage] = {}

    for message in history:
        chat_id = message.get("chat_id")
        message_id = message.get("id")

        if chat_id is None or message_id is None:
            continue

        chat_id_s = str(chat_id)
        previous_message = by_chat.get(chat_id_s)

        if previous_message is None:
            by_chat[chat_id_s] = message
            continue

        current_id = safe_int(message_id)
        previous_id = safe_int(previous_message.get("id"))

        if current_id is None or previous_id is None:
            continue

        if current_id >= previous_id:
            by_chat[chat_id_s] = message

    for chat_id_s in pending_chat_ids:
        last_message = by_chat.get(chat_id_s)
        if last_message is None:
            continue

        chat_id = last_message.get("chat_id")
        message_id = last_message.get("id")

        if chat_id is None or message_id is None:
            continue

        message_id_s = str(message_id)
        message_text = extract_message_text(last_message)

        task_text = task_text_reply(
            str(chat_id),
            message_id_s,
            message_text,
        )
        desired_pending_task_texts.add(task_text)

        key = reply_key_from_task_text(task_text)
        if key is not None:
            desired_pending_reply_keys.add(key)

    pending_task_texts_to_queue: list[str] = []

    for task_text in desired_pending_task_texts:
        key = reply_key_from_task_text(task_text)

        if key is not None and key in existing_open_reply_keys:
            continue

        pending_task_texts_to_queue.append(task_text)

    logger.info(
        "Todo_list_manager: Reply-to tasks to add: "
        + "%d pending after dedupe; removals chats: %d",
        len(pending_task_texts_to_queue),
        len(responded_chat_ids),
    )


    # responded chats -> remove their existing open reply-to tasks (separate batch)
    if responded_chat_ids:
        for cid in responded_chat_ids:
            if cid in blacklisted_chat_ids:
                continue

            existing_task_ids_for_chat = existing_reply_tasks_by_chat.get(cid, [])
            logger.info(
                "Todo_list_manager: Reply-to removals: chat_id=%s matching_existing=%d",
                cid,
                len(existing_task_ids_for_chat),
            )
            for task_id in existing_task_ids_for_chat:
                queue_remove_task(
                    edits_to_apply=edits_remove_batch,
                    todo_list_id=str(TG_TODO_LIST_ID),
                    task_id=task_id,
                )

    # ----- Batch A: apply adds first -----
    graph_after_add = current
    edits_add_batch: list[TodoEdit] = []
    queued_task_texts: set[str] = set()

    # If the todo list is missing, make sure add_todo_list is the FIRST edit in this batch
    if pending_task_texts_to_queue or did_blacklist_removals or responded_chat_ids:
        _ = ensure_todo_list_if_missing(
            current=current,
            edits_to_apply=edits_add_batch,  # ensures add_todo_list is queued into THIS batch
            ensured_todo_list=False,
            list_id=str(TG_TODO_LIST_ID),
            title=TG_TODO_LIST_TITLE,
        )

    for task_text in pending_task_texts_to_queue:
        logger.debug("Todo_list_manager: Queueing reply-to pending task.")
        queue_add_task(
            current=graph_after_add,
            task_text=task_text,
            queued_task_texts=queued_task_texts,
            edits_to_apply=edits_add_batch,  # tasks go after add_todo_list
            list_id=str(TG_TODO_LIST_ID),
        )

    if edits_add_batch:
        todo_params_add: TodoParams = (
            edits_add_batch[0]
            if len(edits_add_batch) == 1
            else as_todo_params_sequential(edits_add_batch)
        )

        graph_after_add = await _run_todo_list_workflow(
            graph_after_add,
            todo_params_add,
            workflow_path,
        )

    # If nothing to remove, just do deadline logic on the added result (if requested)
    if not edits_remove_batch:
        if deadline is None:
            return graph_after_add

        task_ids_to_deadline_added: list[str] = []

        for todo_list in graph_after_add.todo_lists:
            if todo_list.id != str(TG_TODO_LIST_ID):
                continue

            for task in todo_list.tasks:
                if task.completed:
                    continue

                # Only set the deadline when it is currently missing.
                if task.deadline is not None:
                    continue

                task_text = task.text.strip()
                key = reply_key_from_task_text(task_text)

                if key is not None and key in desired_pending_reply_keys:
                    task_ids_to_deadline_added.append(task.id)

        if not task_ids_to_deadline_added:
            return graph_after_add

        deadline_edits_add_batch: list[TodoEdit] = []
        for task_id in task_ids_to_deadline_added:
            logger.debug("Todo_list_manager: Queueing set_deadline for task_id=%r", task_id)
            queue_set_deadline_for_task(
                edits_to_apply=deadline_edits_add_batch,
                task_id=str(task_id),
                deadline=deadline,
                TG_TODO_LIST_ID=str(TG_TODO_LIST_ID),
            )

        if not deadline_edits_add_batch:
            return graph_after_add

        final_graph_added = await _run_todo_list_workflow(
            graph_after_add,
            as_todo_params_sequential(deadline_edits_add_batch),
            workflow_path,
        )

        return dedupe_graph_tasks_and_lists(
            final_graph_added,
            todo_list_id=str(TG_TODO_LIST_ID),
        )


    # ----- Batch B: apply removals second -----
    todo_params_remove = as_todo_params_sequential(edits_remove_batch)

    graph_after_remove = await _run_todo_list_workflow(
        graph_after_add,
        todo_params_remove,
        workflow_path,
    )

    graph_after_remove = dedupe_graph_tasks_and_lists(
        graph_after_remove,
        todo_list_id=str(TG_TODO_LIST_ID),
    )

    # If no deadline was requested, return after applying removals.
    if deadline is None:
        return graph_after_remove


    # ----- Batch #2 (after removals): set deadlines on remaining pending tasks -----
    task_ids_to_deadline_after_remove: list[str] = []
    target_list_id = str(TG_TODO_LIST_ID)

    for todo_list in graph_after_remove.todo_lists:
        if todo_list.id != target_list_id:
            continue

        for task in todo_list.tasks:
            if task.completed:
                continue

            # Only set the deadline when it is currently missing.
            if task.deadline is not None:
                continue

            task_text = task.text.strip()
            key = reply_key_from_task_text(task_text)

            if key is not None and key in desired_pending_reply_keys:
                task_ids_to_deadline_after_remove.append(task.id)

    if not task_ids_to_deadline_after_remove:
        return graph_after_remove

    deadline_edits_after_remove: list[TodoEdit] = []
    for task_id in task_ids_to_deadline_after_remove:
        logger.debug("Todo_list_manager: Queueing set_deadline for task_id=%r", task_id)
        queue_set_deadline_for_task(
            edits_to_apply=deadline_edits_after_remove,
            task_id=str(task_id),
            deadline=deadline,
            TG_TODO_LIST_ID=str(TG_TODO_LIST_ID),
        )

    if not deadline_edits_after_remove:
        return graph_after_remove

    final_graph = await _run_todo_list_workflow(
        graph_after_remove,
        as_todo_params_sequential(deadline_edits_after_remove),
        workflow_path,
    )

    logger.info(
        "Todo_list_manager: Adds+removals applied: removed_edits=%d added_edits=%d todo_list_id=%s",
        len(edits_remove_batch),
        len(edits_add_batch),
        str(TG_TODO_LIST_ID),
    )

    return dedupe_graph_tasks_and_lists(
        final_graph,
        todo_list_id=str(TG_TODO_LIST_ID),
    )


# --- Add a bunch of tasks at Workflow Designer follow-up rounds ---

async def augment_graph_with_client_tasks(
    graph: ProcessGraph,
    edits: Sequence[object] | None,
    *,
    coding_is_allowed: bool,
    workflow_path: Path | None = None,
) -> tuple[ProcessGraph, list[str]]:
    supplements: list[str] = []

    current = graph
    edits_to_apply: list[TodoEdit] = []
    ensured_todo_list = False
    queued_task_texts: set[str] = set()

    def ensure_list() -> None:
        """Ensure the shared graph todo list is added exactly once."""
        nonlocal ensured_todo_list

        if ensured_todo_list:
            return

        _ = ensure_todo_list_if_missing(
            current=current,
            edits_to_apply=edits_to_apply,
            ensured_todo_list=ensured_todo_list,
            list_id=GRAPH_TODO_LIST_ID,
            title=GRAPH_TODO_LIST_TITLE,
        )
        ensured_todo_list = True

    def queue_task(task_text: str) -> None:
        queue_add_task(
            current=current,
            task_text=task_text,
            queued_task_texts=queued_task_texts,
            edits_to_apply=edits_to_apply,
            list_id=GRAPH_TODO_LIST_ID,
        )

    # Collect added unit IDs while preserving edit order.
    added_unit_ids: list[str] = []

    for edit in edits or ():
        unit = get_added_unit(edit)
        if unit is None:
            continue

        unit_id = unit.get("id")
        if isinstance(unit_id, str) and unit_id.strip():
            added_unit_ids.append(unit_id.strip())


    ordered_unit_ids = list(dict.fromkeys(added_unit_ids))

    if ordered_unit_ids:
        supplements.append(
            "client: todo tasks for add_unit (connections + params)"
        )

        unit_ids = ", ".join(ordered_unit_ids)

        ensure_list()
        queue_task(
            TASK_ENSURE_UNITS_CONNECTED.format(unit_ids=unit_ids)
        )
        queue_task(
            TASK_CHECK_UNITS_PARAMS.format(unit_ids=unit_ids)
        )

    # Add run_workflow follow-up tasks.
    has_run_workflow = any(
        has_action(edit, "run_workflow")
        for edit in edits or ()
    )

    if has_run_workflow:
        supplements.append(
            "client: todo tasks for run_workflow (debug + initial data)"
        )

        ensure_list()
        queue_task(TASK_ENSURE_DEBUG_FOR_RUN)
        queue_task(TASK_PREPARE_INITIAL_DATA_FOR_RUN)

    # Add code-block tasks for newly added Function/Script units.
    code_unit_ids: list[str] = []

    for edit in edits or ():
        unit = get_added_unit(edit)
        if unit is None:
            continue

        unit_type = unit.get("type")
        unit_id = unit.get("id")

        if (
            isinstance(unit_type, str)
            and unit_type.strip().lower() in {"function", "script"}
            and isinstance(unit_id, str)
            and unit_id.strip()
        ):
            code_unit_ids.append(unit_id.strip())

        code_unit_ids = list(dict.fromkeys(code_unit_ids))

        for unit_id in code_unit_ids:
            ensure_list()
            queue_task(TASK_PREFIX_ADD_CODE_BLOCK + unit_id)

        if code_unit_ids:
            supplements.append("client: todo task for code block unit")

    # Add imported-workflow review task.
    has_import_workflow = any(
        has_action(edit, "import_workflow")
        for edit in edits or ()
    )

    if has_import_workflow:
        supplements.append('client: todo task "Review the workflow"')

        ensure_list()
        queue_task(TASK_REVIEW_IMPORTED_WORKFLOW)

    if not edits_to_apply:
        return current, supplements

    # TodoParams is a typed union, so construct the wrapper explicitly.
    todo_params: TodoParams = as_todo_params_sequential(edits_to_apply)

    updated = await _run_todo_list_workflow(
        current,
        todo_params,
        workflow_path,
    )

    return updated, supplements
