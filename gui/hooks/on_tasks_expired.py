"""
A workflow helper that:
   - detects expired Telegram-related todo tasks in the latest graph,
   - updates the corresponding todo list/tasks, saves the updated workflow,
   - triggers new agentic handle_turn loop to get the tasks DONE.
"""
import json
from typing import Any
from pathlib import Path
import logging
import time
from gui.chat.context.todo_list_manager import TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE
from gui.chat.utils.workflow_manager import import_latest_workflow_graph_async
from gui.chat.context.todo_list_manager import add_tasks_for_unhandled_tg_messages
from gui.components.settings import (
    TG_TODO_LIST_ID,
    TG_TODO_LIST_TITLE,
    get_todo_task_deadline_s,
)

logger = logging.getLogger(__name__)

TODO_TASK_DEADLINE = get_todo_task_deadline_s()

# Prompt line passed on the user's behalf when the expired tasks todo are detected
TODO_TASKS_EXPIRED_USER_MESSAGE_TEMPLATE = (
    "You still have some tasks to do. You have to finish the tasks: {tasks_expired}  "
)

def _parse_reply_to_chat_id_from_task_text(task_text: str) -> str | None:
    text = (task_text or "").strip()
    if not text.startswith(TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE):
        return None
    payload_str = text[len(TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE) :].strip()
    try:
        payload = json.loads(payload_str) if payload_str else {}
    except Exception:
        return None
    chat_id = payload.get("chat_id")
    return None if chat_id is None else str(chat_id)

def _parse_deadline_ts(deadline_value: Any) -> float | None:
    if deadline_value is None:
        return None
    s = str(deadline_value).strip()
    if not s or s.lower() == "null":
        return None
    try:
        return float(s)
    except Exception:
        return None

async def _handle_tasks_expired_hook(
    *,
    handle_turn,
    sess: str,
    out_session: str,          # matches chat_id on telegram
    MESSENGER: str,
    workflow_path: Path | None,
    max_followups: int = 3,
    now_ts: float | None = None,
    **handle_turn_kwargs: Any, # additional parameters supported by handle_turn
) -> None:
    if now_ts is None:
        now_ts = time.time()

    def _compute_expired(graph: dict[str, Any], now_ts_: float) -> list[dict[str, Any]]:
        tasks_expired_: list[dict[str, Any]] = []
        todo_lists = graph.get("todo_lists")
        if not isinstance(todo_lists, list):
            return tasks_expired_

        wanted_chat_id = str(out_session)

        for tl in todo_lists:
            if not isinstance(tl, dict) or tl.get("id") != TG_TODO_LIST_ID:
                continue
            tasks = tl.get("tasks")
            if not isinstance(tasks, list):
                continue

            for t in tasks:
                if not isinstance(t, dict):
                    continue
                if t.get("completed"):
                    continue

                t_text = (t.get("text") or "").strip()
                chat_id_from_text = _parse_reply_to_chat_id_from_task_text(t_text)
                if chat_id_from_text != wanted_chat_id:
                    continue

                dl = _parse_deadline_ts(t.get("deadline"))
                if dl is None:
                    continue
                if dl < now_ts_:
                    tasks_expired_.append(
                        {
                            "id": t.get("id"),
                            "text": t_text,
                            "deadline": t.get("deadline"),
                        }
                    )
        return tasks_expired_

    followups = 0

    while followups < max_followups:
        followups += 1

        graph_result = await import_latest_workflow_graph_async()
        if getattr(graph_result, "error", None):
            return

        graph_dict = getattr(graph_result, "graph", None)
        if not isinstance(graph_dict, dict):
            return

        now_ts = time.time()
        tasks_expired = _compute_expired(graph_dict, now_ts)
        if not tasks_expired:
            return

        # --- add todo tasks into the imported graph before follow-up turn ---
        edits_to_apply: list[dict[str, Any]] = []
        ensured_todo_list_if_missing = False
        current_graph = graph_dict

        async def ensure_todo_list_if_missing() -> None:
            nonlocal ensured_todo_list_if_missing, edits_to_apply
            if ensured_todo_list_if_missing:
                return
            ensured_todo_list_if_missing = True
            edits_to_apply.append(
                {"action": "add_todo_list", "id": TG_TODO_LIST_ID, "title": TG_TODO_LIST_TITLE}
            )

        def queue_add_task(task_text: str) -> None:
            text = (task_text or "").strip()
            if not text:
                return

            todo_lists = current_graph.get("todo_lists")
            if isinstance(todo_lists, list):
                for tl in todo_lists:
                    if not isinstance(tl, dict):
                        continue
                    if str(tl.get("id")) != str(TG_TODO_LIST_ID):
                        continue
                    tasks = tl.get("tasks")
                    if not isinstance(tasks, list):
                        continue
                    for t in tasks:
                        if not isinstance(t, dict) or t.get("completed"):
                            continue
                        if (t.get("text") or "").strip() == text:
                            return

            edits_to_apply.append(
                {"action": "add_task", "todo_list_id": str(TG_TODO_LIST_ID), "text": text}
            )

        for te in tasks_expired:
            queue_add_task(te.get("text") or "")

        updated = await add_tasks_for_unhandled_tg_messages(
            current=current_graph,
            edits_to_apply=edits_to_apply,
            ensure_todo_list_if_missing=ensure_todo_list_if_missing,
            queue_add_task=queue_add_task,
            workflow_path=None,
            deadline=TODO_TASK_DEADLINE,
        )
        if updated is not None:
            graph_dict = updated

        # --- Save updated workflow ---
        if graph_dict is not None:
            from gui.utils import save_workflow_version

            save_res = save_workflow_version(graph_dict)
            if save_res.saved:
                logger.info("session=%s: workflow saved path=%s", sess, save_res.path)
            elif save_res.reason == "no_changes":
                logger.info(
                    "session=%s: workflow not changed; using latest path=%s",
                    sess,
                    save_res.path,
                )
            else:
                logger.warning(
                    "session=%s: workflow save skipped reason=%s",
                    sess,
                    save_res.reason,
                )

        # --- Run new agentic loop ----
        expired_task_ids = [str(t.get("id")) for t in tasks_expired if t.get("id") is not None]

        logger.info(
            "Expired tasks detected: N=%d (task_ids=%s, followup=%d/%d, out_session=%s)",
            len(tasks_expired),
            ",".join(expired_task_ids),
            followups,
            max_followups,
            out_session,
        )

        logger.info(
            "Starting new turn to finish (followup=%d/%d, out_session=%s)",
            followups,
            max_followups,
            out_session,
        )

        user_message = TODO_TASKS_EXPIRED_USER_MESSAGE_TEMPLATE.format(
            tasks_expired=tasks_expired
        )

        outputs = await handle_turn(
            sess,
            user_message,
            MESSENGER,
            graph_dict=graph_dict,
            **handle_turn_kwargs,  # forwards role_id, recent_changes, pre_built_user_msg, on_rename, stream_callback, on_apply, ...
        )
        if outputs is None:
            return
