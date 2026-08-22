import logging

from pydantic import ValidationError

from agents.chat.context.todo_list_manager import (
    TodoEdit,
    add_tasks_for_unhandled_tg_messages,
    ensure_todo_list_if_missing,
    queue_add_task,
)
from agents.chat.turn_driver import handle_turn
from agents.chat.utils.workflow_manager import import_latest_workflow_graph_async
from core.schemas import ProcessGraph, TodoTask
from gui.components.settings import (
    get_todo_task_deadline_s,
)
from gui.hooks.on_tasks_expired import handle_tasks_expired_hook
from messengers_integrations.messenger_state import MessengerChatUpdate
from services.agentic_loop import cfg_helpers as cfg
from services.logging import setup_colored_logging

from .prompts import (
    GET_CHATS_FOLLOW_UP_USER_MESSAGE_TEMPLATE,
    TODO_TASKS_INCOMPLETE_USER_MESSAGE_TEMPLATE,
)

logger = setup_colored_logging(logging.INFO)

TODO_TASK_DEADLINE = get_todo_task_deadline_s()
DEFAULT_MESSENGER = cfg.default_messenger


async def run_agentic_loop(
    sess: str | None,
    *,
    messenger: str = DEFAULT_MESSENGER,
    user_message_template: str | None = None,
    unread_chats: list[MessengerChatUpdate] | None = None,
    incomplete_tasks: list[TodoTask] | None = None,
) -> None:
    """
    Run an agentic turn for either unread chats or incomplete todo tasks.

    Exactly one of unread_chats or incomplete_tasks must be provided.

    A custom user_message_template must contain:
    - {unread_chats} when unread_chats is provided
    - {incomplete_tasks} when incomplete_tasks is provided
    """
    if (unread_chats is None) == (incomplete_tasks is None):
        raise ValueError(
            "Provide exactly one of unread_chats or incomplete_tasks"
        )

    if unread_chats is not None:
        if not unread_chats:
            logger.info(
                "session=%s: no unread chats supplied; skipping agentic turn",
                sess,
            )
            return

        template = (
            user_message_template
            or GET_CHATS_FOLLOW_UP_USER_MESSAGE_TEMPLATE
        )

        if (
            user_message_template is not None
            and "{unread_chats}" not in user_message_template
        ):
            raise ValueError(
                "user_message_template must contain {unread_chats}"
            )

        user_message = template.format(unread_chats=unread_chats)

    else:
        if not incomplete_tasks:
            logger.info(
                "session=%s: no incomplete tasks supplied; skipping agentic turn",
                sess,
            )
            return

        template = (
            user_message_template
            or TODO_TASKS_INCOMPLETE_USER_MESSAGE_TEMPLATE
        )

        if (
            user_message_template is not None
            and "{incomplete_tasks}" not in user_message_template
        ):
            raise ValueError(
                "user_message_template must contain {incomplete_tasks}"
            )


        user_message = template.format(
            incomplete_tasks=incomplete_tasks,
        )

    logger.info(
        "Starting agentic turn: session=%s, messenger=%s, unread_chats=%s, incomplete_tasks=%s",
        sess,
        messenger,
        unread_chats is not None,
        incomplete_tasks is not None,
    )

    try:
        from agents.chat.graph_bridge import get_live_graph_dict

        graph_dict = get_live_graph_dict()

        if graph_dict is not None:
            graph = ProcessGraph.model_validate(graph_dict)

            logger.info(
                "session=%s: using live canvas graph (units=%d todo_lists=%d)",
                sess,
                len(graph.units),
                len(graph.todo_lists),
            )
        else:
            graph_result = await import_latest_workflow_graph_async()

            if graph_result.error:
                logger.error(
                    "session=%s: failed to import workflow graph: %s",
                    sess,
                    graph_result.error,
                )
                graph = None
            else:
                graph = ProcessGraph.model_validate(graph_result.graph)

                logger.info(
                    "session=%s: imported graph from %s",
                    sess,
                    graph_result.picked_workflow_path,
                )

        # Add reply-to todo tasks only when processing unread messages.
        if unread_chats is not None and graph is not None:

            current_graph: ProcessGraph = graph
            edits_to_apply: list[TodoEdit] = []

            updated_graph_dict = await add_tasks_for_unhandled_tg_messages(
                current=current_graph,
                edits_to_apply=edits_to_apply,
                ensure_todo_list_if_missing=ensure_todo_list_if_missing,
                queue_add_task=queue_add_task,
                workflow_path=None,
                deadline=TODO_TASK_DEADLINE,
            )

            if updated_graph_dict is not None:
                graph = ProcessGraph.model_validate(updated_graph_dict)


        # Save graph changes before running the turn.
        if graph is not None:
            from agents.chat.utils import save_workflow_version

            try:
                save_result = save_workflow_version(graph)
            except (ValidationError, TypeError):
                logger.exception(
                    "session=%s: failed to save invalid workflow graph",
                    sess,
                )
                save_result = None

            if save_result is not None:
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
            messenger,
            graph_dict=graph,
        )


    except Exception:
        logger.exception("session=%s: agentic turn failed", sess)
        return

    if outputs is None:
        logger.warning("session=%s: handle_turn returned None", sess)
        return

    out_session = sess

    message = outputs.get("message")

    if isinstance(message, dict):
        message_session: object = message.get("session_id")

        if isinstance(message_session, str) and message_session:
            out_session = message_session

    hook_session = out_session or ""

    await handle_tasks_expired_hook(
        handle_turn=handle_turn,
        sess=hook_session,
        out_session=hook_session,
        MESSENGER=messenger,
        workflow_path=None,
    )

    logger.info("session=%s: agentic turn completed", out_session)
