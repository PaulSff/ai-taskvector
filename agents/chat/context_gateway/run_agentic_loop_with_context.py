import logging
from typing import Any

from pydantic import ValidationError

from agents.chat.context.todo_list_manager import (
    add_tasks_for_unhandled_tg_messages,
)
from agents.chat.session import create_session
from agents.chat.turn_driver import handle_turn
from agents.chat.utils.workflow_manager import import_latest_workflow_graph_async
from core.schemas import ProcessGraph
from gui.components.settings import (
    TG_TODO_LIST_ID,
    TG_TODO_LIST_TITLE,
    get_todo_task_deadline_s,
)
from gui.hooks.on_tasks_expired import handle_tasks_expired_hook
from services.logging import setup_colored_logging

from .prompts import (
    GET_CHATS_FOLLOW_UP_USER_MESSAGE_TEMPLATE,
    TODO_TASKS_INCOMPLETE_USER_MESSAGE_TEMPLATE,
)

logger = setup_colored_logging(logging.INFO)

TODO_TASK_DEADLINE = get_todo_task_deadline_s()


async def run_agentic_turn(
    *,
    unread_chats: list[dict[str, Any]] | None = None,
    incomplete_tasks: list[dict[str, Any]] | None = None,
) -> None:
    """
    Create a session and run an agentic turn for either unread Telegram chats
    or incomplete todo tasks.

    Exactly one of unread_chats or incomplete_tasks must be provided.
    """

    if (unread_chats is None) == (incomplete_tasks is None):
        raise ValueError(
            "Provide exactly one of unread_chats or incomplete_tasks"
        )

    if unread_chats is not None:
        if not unread_chats:
            logger.info("No unread chats supplied; skipping agentic turn")
            return

        first_chat = unread_chats[0]
        session_id = (
            first_chat.get("session_id")
            or first_chat.get("chat_id")
            or first_chat.get("id")
            or first_chat.get("peer_id")
        )

        if session_id is None:
            raise ValueError(
                "Unread chat does not contain a session_id, chat_id, id, or peer_id"
            )

        user_message = GET_CHATS_FOLLOW_UP_USER_MESSAGE_TEMPLATE.format(
            unread_chats=unread_chats
        )

    else:
        if not incomplete_tasks:
            logger.info("No incomplete tasks supplied; skipping agentic turn")
            return

        first_task = incomplete_tasks[0]
        todo_list_id = first_task.get("todo_list_id")

        if todo_list_id is None:
            raise ValueError(
                "Incomplete task does not contain a todo_list_id"
            )

        session_id = str(todo_list_id)

        user_message = TODO_TASKS_INCOMPLETE_USER_MESSAGE_TEMPLATE.format(
            incomplete_tasks=incomplete_tasks
        )

    sess = create_session(str(session_id))

    logger.info(
        "Starting agentic turn: session=%s, unread_chats=%s, incomplete_tasks=%s",
        sess,
        unread_chats is not None,
        incomplete_tasks is not None,
    )

    try:
        # Get the current graph.
        from agents.chat.graph_bridge import get_live_graph_dict

        graph_dict = get_live_graph_dict()

        if graph_dict is not None:
            logger.info(
                "session=%s: using live canvas graph (units=%d todo_lists=%d)",
                sess,
                len(graph_dict.get("units") or []),
                len(graph_dict.get("todo_lists") or []),
            )
        else:
            graph_result = await import_latest_workflow_graph_async()
            graph_dict = graph_result.graph

            if graph_result.error:
                logger.error(
                    "session=%s: failed to import workflow graph: %s",
                    sess,
                    graph_result.error,
                )
                graph_dict = None
            else:
                logger.info(
                    "session=%s: imported graph from %s",
                    sess,
                    graph_result.picked_workflow_path,
                )

        # Add reply-to todo tasks only when processing unread messages.
        if unread_chats is not None and graph_dict is not None:
            edits_to_apply: list[dict[str, Any]] = []
            ensured_todo_list = False
            current_graph = graph_dict

            async def ensure_todo_list_if_missing() -> None:
                nonlocal ensured_todo_list

                if ensured_todo_list:
                    return

                ensured_todo_list = True
                edits_to_apply.append(
                    {
                        "action": "add_todo_list",
                        "id": TG_TODO_LIST_ID,
                        "title": TG_TODO_LIST_TITLE,
                    }
                )

            def queue_add_task(task_text: str) -> None:
                text = (task_text or "").strip()
                if not text:
                    return

                todo_lists = current_graph.get("todo_lists")
                if isinstance(todo_lists, list):
                    for todo_list in todo_lists:
                        if not isinstance(todo_list, dict):
                            continue

                        if str(todo_list.get("id")) != str(TG_TODO_LIST_ID):
                            continue

                        tasks = todo_list.get("tasks")
                        if not isinstance(tasks, list):
                            continue

                        for task in tasks:
                            if not isinstance(task, dict):
                                continue
                            if task.get("completed"):
                                continue
                            if (task.get("text") or "").strip() == text:
                                return

                edits_to_apply.append(
                    {
                        "action": "add_task",
                        "todo_list_id": str(TG_TODO_LIST_ID),
                        "text": text,
                    }
                )

            updated_graph = await add_tasks_for_unhandled_tg_messages(
                current=current_graph,
                edits_to_apply=edits_to_apply,
                ensure_todo_list_if_missing=ensure_todo_list_if_missing,
                queue_add_task=queue_add_task,
                workflow_path=None,
                deadline=TODO_TASK_DEADLINE,
            )

            if updated_graph is not None:
                graph_dict = updated_graph

        # Save graph changes before running the turn.
        if graph_dict is not None:
            from agents.chat.utils import save_workflow_version

            try:
                graph = ProcessGraph.model_validate(graph_dict)
            except (ValidationError, TypeError):
                graph = None

            save_result = save_workflow_version(graph)

            if save_result.saved:
                logger.info(
                    "session=%s: workflow saved at %s",
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

        outputs = await handle_turn(
            sess,
            user_message,
            "telegram",
            graph_dict=graph_dict,
        )

    except Exception:
        logger.exception("session=%s: agentic turn failed", sess)
        return

    if outputs is None:
        logger.warning("session=%s: handle_turn returned None", sess)
        return

    out_session = sess
    if isinstance(outputs, dict):
        message = outputs.get("message")
        if isinstance(message, dict) and message.get("session_id"):
            out_session = message["session_id"]

    await handle_tasks_expired_hook(
        handle_turn=handle_turn,
        sess=sess,
        out_session=str(out_session),
        MESSENGER="telegram",
        workflow_path=None,
    )

    logger.info("session=%s: agentic turn completed", out_session)
