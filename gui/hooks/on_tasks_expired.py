"""
A workflow helper that:
   - detects expired Telegram-related todo tasks in the latest graph,
   - updates the corresponding todo list/tasks, saves the updated workflow,
   - triggers new agentic handle_turn loop to get the tasks DONE.
"""
import json
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agents.chat.context.todo_list_manager import (
    TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE,
    TodoEdit,
    add_tasks_for_unhandled_messages,
    ensure_todo_list_if_missing,
    queue_add_task,
)
from agents.chat.utils.workflow_manager import import_latest_workflow_graph_async
from core.schemas import ProcessGraph, TodoTask
from gui.components.settings import (
    TG_TODO_LIST_ID,
    get_todo_task_deadline_s,
)

logger = logging.getLogger(__name__)

TODO_TASK_DEADLINE = get_todo_task_deadline_s()

# Prompt line passed on the user's behalf when the expired tasks todo are detected
TODO_TASKS_EXPIRED_USER_MESSAGE_TEMPLATE = (
    "You still have some tasks to do. You have to finish the tasks: {tasks_expired}  "
)

DEFAULT_MAX_AGENTIC_LOOP_FOLLOW_UPS = 3


# --- Helpers ---
def _parse_reply_to_chat_id_from_task_text(task_text: str) -> str | None:
    text = (task_text or "").strip()
    if not text.startswith(TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE):
        return None

    payload_str = text[len(TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE):].strip()

    try:
        payload = json.loads(payload_str) if payload_str else {}
    except json.JSONDecodeError:
        return None

    chat_id = payload.get("chat_id")
    return None if chat_id is None else str(chat_id)


def _parse_deadline_ts(deadline_value: str | None) -> float | None:
    if deadline_value is None:
        return None

    value = deadline_value.strip()

    if not value or value.lower() == "null":
        return None

    try:
        return float(value)
    except ValueError:
        return None


# ---- End of the helpers ----

HandleTurn = Callable[
    ...,
    Awaitable[dict[str, object] | None],
]

async def handle_tasks_expired_hook(
    *,
    handle_turn: HandleTurn,
    sess: str,
    out_session: str,
    MESSENGER: str,
    workflow_path: Path | None,
    max_followups: int = DEFAULT_MAX_AGENTIC_LOOP_FOLLOW_UPS,
    now_ts: float | None = None,
    **handle_turn_kwargs: Any,
) -> None:
    if now_ts is None:
        now_ts = time.time()

    def _compute_expired(
        graph: ProcessGraph,
        now_ts_: float,
    ) -> list[TodoTask]:
        tasks_expired: list[TodoTask] = []
        wanted_chat_id = str(out_session)

        for todo_list in graph.todo_lists:
            if todo_list.id != str(TG_TODO_LIST_ID):
                continue

            for task in todo_list.tasks:
                if task.completed:
                    continue

                task_text = task.text.strip()

                chat_id_from_text = (
                    _parse_reply_to_chat_id_from_task_text(task_text)
                )
                if chat_id_from_text != wanted_chat_id:
                    continue

                deadline_ts = _parse_deadline_ts(task.deadline)
                if deadline_ts is None:
                    continue

                if deadline_ts < now_ts_:
                    tasks_expired.append(task)

        return tasks_expired

    followups = 0

    while followups < max_followups:
        followups += 1

        graph_result = await import_latest_workflow_graph_async()

        if getattr(graph_result, "error", None):
            logger.warning(
                "session=%s: failed to import workflow graph: %s",
                sess,
                graph_result.error,
            )
            return

        graph_data = getattr(graph_result, "graph", None)
        if not isinstance(graph_data, dict):
            logger.warning(
                "session=%s: imported workflow graph is invalid",
                sess,
            )
            return

        try:
            current_graph = ProcessGraph.model_validate(graph_data)
        except (ValidationError, TypeError):
            logger.exception(
                "session=%s: failed to validate imported workflow graph",
                sess,
            )
            return

        current_now_ts = time.time()
        tasks_expired = _compute_expired(
            current_graph,
            current_now_ts,
        )

        if not tasks_expired:
            return

        edits_to_apply: list[TodoEdit] = []
        queued_task_texts: set[str] = set()

        # Re-queue the expired tasks through the shared helper. The helper
        # handles task normalization and duplicate detection.
        for expired_task in tasks_expired:
            queue_add_task(
                current=current_graph,
                edits_to_apply=edits_to_apply,
                queued_task_texts=queued_task_texts,
                task_text=expired_task.text,
            )

        # Add reply-to tasks for any newly unhandled Telegram messages using
        # the same helper flow as the main agentic loop.
        updated_graph_dict = await add_tasks_for_unhandled_messages(
            current=current_graph,
            edits_to_apply=edits_to_apply,
            ensure_todo_list_if_missing=ensure_todo_list_if_missing,
            queue_add_task=queue_add_task,
            workflow_path=workflow_path,
            deadline=TODO_TASK_DEADLINE,
        )

        if updated_graph_dict is not None:
            graph_dict = updated_graph_dict
        else:
            graph_dict = current_graph.model_dump()

        try:
            graph = ProcessGraph.model_validate(graph_dict)
        except (ValidationError, TypeError):
            logger.exception(
                "session=%s: failed to validate updated workflow graph",
                sess,
            )
            return

        from agents.chat.utils import save_workflow_version

        try:
            save_result = save_workflow_version(graph)
        except (ValidationError, TypeError):
            logger.exception(
                "session=%s: failed to save updated workflow graph",
                sess,
            )
            return

        if save_result.saved:
            logger.info(
                "session=%s: workflow saved path=%s",
                sess,
                save_result.path,
            )
        elif save_result.reason == "no_changes":
            logger.info(
                "session=%s: workflow unchanged; using %s",
                sess,
                save_result.path,
            )
        else:
            logger.warning(
                "session=%s: workflow save skipped: %s",
                sess,
                save_result.reason,
            )

        graph_dict = graph.model_dump()

        expired_task_ids = [str(task.id) for task in tasks_expired]

        logger.info(
            (
                "Expired tasks detected: N=%d task_ids=%s followup=%d/%d out_session=%s"
            ),
            len(tasks_expired),
            ",".join(expired_task_ids),
            followups,
            max_followups,
            out_session,
        )

        user_message = TODO_TASKS_EXPIRED_USER_MESSAGE_TEMPLATE.format(
            tasks_expired=tasks_expired,
        )

        outputs = await handle_turn(
            sess,
            user_message,
            MESSENGER,
            graph_dict=graph_dict,
            **handle_turn_kwargs,
        )

        if outputs is None:
            logger.warning(
                "session=%s: handle_turn returned None for expired tasks",
                sess,
            )
            return

        next_session = sess
        message = outputs.get("message")

        if isinstance(message, dict):
            message_session = message.get("session_id")

            if isinstance(message_session, str) and message_session:
                next_session = message_session

        sess = next_session
        out_session = next_session
