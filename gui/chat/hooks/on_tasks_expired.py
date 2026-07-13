
import json
from typing import Any
from pathlib import Path
import logging
import time
from gui.chat.context.todo_list_manager import TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE
from gui.components.settings import TG_TODO_LIST_ID
from gui.chat.utils.workflow_manager import import_latest_workflow_graph_async

logger = logging.getLogger(__name__)

# Prompt line passed on the user's behalf when the expired tasks todo are detected
TODO_TASKS_EXPIRED_USER_MESSAGE_TEMPLATE = (
    "You still have some tasks todo. Finish the tasks: {tasks_expired}  "
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
    graph_dict: dict[str, Any] | None = None

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

        expired_task_ids = [
            str(t.get("id")) for t in tasks_expired if t.get("id") is not None
        ]

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
        )
        if outputs is None:
            return
