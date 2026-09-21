"""
Async agent turn runner: unpacks context dict and drives the full orchestration pipeline.

Called from AgentOrchestrator._agent_orchestrator_step (sync unit step function).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import cast

from agents.chat.agent_workflow import AgentWorkflowResponse
from agents.chat.context.role_turn_context import RoleChatTurnContext
from agents.chat.handlers.chat_turn_context import (
    normalize_user_message_for_workflow,
)
from agents.chat.role_turns.registry import get_role_chat_handler
from agents.chat.session.state import AgentChatHistory, ChatSessionState
from agents.roles.registry import WORKFLOW_DESIGNER_ROLE_ID, get_role
from core.normalizer.normalizer import graph_to_json_object
from core.normalizer.shared import to_json_value
from core.schemas import ProcessGraph
from core.schemas.graph_edit_api import (
    AgentApplyWorkflowEditsResult,
    ApplyWorkflowEditsResult,
)
from core.schemas.primitives import Data
from runtime.executor import GraphStreamCallback
from runtime.run import INLINE_STATUS_FOR_STREAMING
from runtime.stream_ui_signals import inline_status_stream_chunk
from units.taskvector.agent_orchestrator.utils.batch_update_helpers import (
    ProgressResponse,
    make_publish_in_progress,
)
from units.taskvector.agent_orchestrator.utils.batch_update_publisher import (
    BatchUpdatePublisher,
)
from units.taskvector.agent_orchestrator.utils.ids import new_id
from units.taskvector.agent_orchestrator.utils.proxies import (
    SessionProxy,
    TurnRuntimeProxy,
)
from units.taskvector.agent_orchestrator.utils.time import now_ts

logger = logging.getLogger(__name__)


async def run_orchestrator_turn(
    context: Data,
    *,
    stream_callback: GraphStreamCallback | None = None,
    batch_update_publisher: BatchUpdatePublisher | None = None,
    run_id: str | None,
) -> Data:
    """
    Role-handler orchestration layer.
    """

    run_output: Data = {}

    raw_graph = context.get("graph")
    if raw_graph is None:
        raise ValueError("Missing process graph")

    graph = ProcessGraph.model_validate(raw_graph)

    user_message = normalize_user_message_for_workflow(
        context.get("user_message") or "",
    )

    messenger = str(context.get("messenger") or "")

    role_id = (
        str(
            context.get("role_id")
            or context.get("role_hint")
            or WORKFLOW_DESIGNER_ROLE_ID,
        ).strip()
        or WORKFLOW_DESIGNER_ROLE_ID
    )

    raw_history = context.get("history")
    history: AgentChatHistory = (
        list(raw_history)
        if isinstance(raw_history, list)
        else []
    )

    session_language = str(context.get("session_language") or "")

    raw_last_apply_result = context.get("last_apply_result")
    last_apply_result: ApplyWorkflowEditsResult | None = (
        ApplyWorkflowEditsResult.model_validate(raw_last_apply_result)
        if raw_last_apply_result is not None
        else None
    )

    raw_recent_changes = context.get("recent_changes")
    recent_changes: str | None = (
        raw_recent_changes
        if isinstance(raw_recent_changes, str)
        else None
    )

    coding_is_allowed = bool(
        context.get("coding_is_allowed", True),
    )
    contribution_is_allowed = bool(
        context.get("contribution_is_allowed", False),
    )

    # initial_graph_md5 = graph_md5(graph)

    graph_ref: list[ProcessGraph] = [graph]
    last_apply_result_ref: list[
        ApplyWorkflowEditsResult | None
    ] = [last_apply_result]

    content_ref: list[str] = [""]
    result_ref: list[AgentApplyWorkflowEditsResult] = [
        AgentApplyWorkflowEditsResult(
            kind="apply_failed",
            content_for_display="",
            graph=graph,
            edits=[],
            last_apply_result=last_apply_result,
        )
    ]
    stream_buffer_ref: list[str] = [""]
    response_ref: list[AgentWorkflowResponse | None] = [None]
    follow_up_contexts_ref: list[list[str]] = [[]]
    apply_meta_ref: list[Data] = [{}]
    error_ref: list[Data | None] = [None]


    def _maybe_thinking_on() -> None:
        callback = stream_callback
        if not callable(callback):
            return

        try:
            callback(
                inline_status_stream_chunk(
                    INLINE_STATUS_FOR_STREAMING,
                ),
            )
        except (TypeError, ValueError):
            return

    def _maybe_thinking_off() -> None:
        callback = stream_callback
        if not callable(callback):
            return

        try:
            callback(inline_status_stream_chunk(None))
        except (TypeError, ValueError):
            return

    def get_progress_response() -> ProgressResponse | None:
        response = response_ref[0]

        if response is None:
            return None

        return {
            "llm_user_message": getattr(
                response,
                "llm_user_message",
                None,
            ),
            "llm_system_prompt": getattr(
                response,
                "llm_system_prompt",
                None,
            ),
        }

    try:
        role_config = get_role(role_id)
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        role_id = WORKFLOW_DESIGNER_ROLE_ID

        try:
            role_config = get_role(role_id)
        except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
            return {
                "status": None,
                "token": None,
                "message": None,
                "role": None,
                "error": {
                    "type": "error",
                    "error": f"Role config failed: {exc}",
                },
            }

    agent_label = role_config.role_name or role_id

    handler = get_role_chat_handler(role_id)
    if handler is None:
        raise ValueError(
            f"No chat handler configured for role: {role_id}",
        )

    # The handler owns this reference when delegation is enabled.
    delegate_request_ref: list[Data | None] | None = cast(
        list[Data | None] | None,
        context.get("delegate_request_ref"),
    )

    if (
        delegate_request_ref is None
        and bool(context.get("auto_delegation_is_allowed", False))
    ):
        delegate_request_ref = [None]

    raw_token = context.get("token")

    if raw_token is None:
        token = 0
    elif isinstance(raw_token, bool):
        # Prevent True/False from being silently treated as 1/0.
        raise TypeError("Context field 'token' must be an integer")
    elif isinstance(raw_token, int):
        token = raw_token
    elif isinstance(raw_token, str):
        try:
            token = int(raw_token)
        except ValueError as exc:
            raise TypeError(
                "Context field 'token' must contain an integer"
            ) from exc
    else:
        raise TypeError(
            "Context field 'token' must be an integer or numeric string"
        )

    raw_state = context.get("state")

    if isinstance(raw_state, ChatSessionState):
        state = raw_state

    elif isinstance(raw_state, dict):
        state_history = raw_state.get("history")

        state_history_value: AgentChatHistory = (
            list(state_history)
            if isinstance(state_history, list)
            else history
        )

        raw_created_at = raw_state.get("created_at")
        created_at = (
            raw_created_at
            if isinstance(raw_created_at, str)
            else ""
        )

        raw_chat_path = raw_state.get("chat_path")
        chat_path = (
            Path(raw_chat_path)
            if isinstance(raw_chat_path, str) and raw_chat_path
            else None
        )

        state = ChatSessionState(
            history=state_history_value,
            busy=bool(raw_state.get("busy", False)),
            has_sent_any=bool(raw_state.get("has_sent_any", False)),
            session_id=str(raw_state.get("session_id") or ""),
            created_at=created_at,
            chat_path=chat_path,
            session_language=str(
                raw_state.get("session_language") or "",
            ),
        )

    else:
        raise TypeError(
            "Context field 'state' must be ChatSessionState or a state mapping, "
            f"got {type(raw_state).__name__}",
        )

    # The parsed state is the authoritative source for session data.
    history = state.history
    session_language = state.session_language or session_language

    raw_turn_id = context.get("turn_id")

    if not isinstance(raw_turn_id, str) or not raw_turn_id.strip():
        raise TypeError(
            "Context field 'turn_id' must be a non-empty string",
        )

    turn_id = raw_turn_id.strip()

    session = SessionProxy(
        session_language=session_language,
        history=history,
    )

    runtime = TurnRuntimeProxy(
        graph_ref=graph_ref,
        stream_callback=stream_callback,
        stream_buffer_ref=stream_buffer_ref,
        state=state,
        token=token,
        recent_changes=recent_changes,
        role_id=role_id,
    )

    _publish_in_progress = make_publish_in_progress(
        batch_update_publisher=batch_update_publisher,
        run_id=run_id,
        get_role_id=lambda: role_id,
        get_agent_label=lambda: agent_label,
        get_turn_id=lambda: turn_id,
        get_messenger=lambda: messenger,
        get_follow_up_contexts=lambda: follow_up_contexts_ref[0],
        get_graph_ref=lambda: graph_ref[0],
        get_last_apply_result=lambda: last_apply_result_ref[0],
        get_result=lambda: result_ref[0],
        get_content=lambda: content_ref[0],
        get_response=get_progress_response,
        get_apply_meta=lambda: apply_meta_ref[0],
        get_session_language=lambda: session.session_language,
        get_run_output=lambda: (
            getattr(response_ref[0], "run_output", {})
            if response_ref[0] is not None
            else {}
        ),
        get_source=lambda: "agent_response",
    )

    turn_context: Data = {
        **context,
        "state": state,
        "user_message": user_message,
        "recent_changes": recent_changes,
        "messenger": messenger,
        "role_id": role_id,
        "provider": str(context.get("provider") or ""),
        "cfg": role_config,
        "auto_delegation_is_allowed": bool(
            context.get("auto_delegation_is_allowed", False),
        ),
        "coding_is_allowed": coding_is_allowed,
        "contribution_is_allowed": contribution_is_allowed,

        "set_graph": runtime.set_graph,
        "is_current_run": runtime.is_current_run,
        "toast": runtime.toast,
        "set_inline_status": runtime.set_inline_status,
        "append_message": runtime.append_message,
        "persist_history_debounced": runtime.persist_history_debounced,
        "workflow_debug_log": runtime.workflow_debug_log,
        "run_workflow_streaming": runtime.run_workflow_streaming,

        "stream_buffer_ref": runtime.stream_buffer_ref,
        "get_recent_changes": runtime.get_recent_changes,
    }

    turn_ctx = RoleChatTurnContext.from_context(
        turn_context,
        graph_ref=graph_ref,
        token=token,
        turn_id=turn_id,
        agent_label=agent_label,
        last_apply_result_ref=last_apply_result_ref,
        delegate_request_ref=delegate_request_ref,
        content_ref=content_ref,
        result_ref=result_ref,
        response_ref=response_ref,
        follow_up_contexts_ref=follow_up_contexts_ref,
        apply_meta_ref=apply_meta_ref,
        error_ref=error_ref,
    )

    try:
        _maybe_thinking_on()

        await handler.run_turn(
            turn_ctx,
            message_for_workflow=user_message,
        )

    except (asyncio.CancelledError, KeyboardInterrupt):
        raise

    except Exception as exc:
        logger.exception(
            "[orchestrator] role handler failed",
            extra={
                "role_id": role_id,
                "turn_id": turn_id,
            },
        )

        error_ref[0] = {
            "type": type(exc).__name__,
            "error": str(exc),
        }

        content_ref[0] = (
            f"(Role handler error: {type(exc).__name__}: {exc})"
        )

        result_ref[0] = AgentApplyWorkflowEditsResult(
                kind="apply_failed",
                content_for_display=content_ref[0],
                graph=graph_ref[0],
                edits=[],
                error_reason=str(exc),
                last_apply_result=None,
            )

        last_apply_result_ref[0] = None

    finally:
        _maybe_thinking_off()

    delegate_request = (
        turn_ctx.delegate_request_ref[0]
        if turn_ctx.delegate_request_ref is not None
        else None
    )

    if (
        isinstance(delegate_request, dict)
        and delegate_request.get("ok") is True
    ):
        delegate_to = str(
            delegate_request.get("delegate_to") or "",
        ).strip().lower()

        if delegate_to and delegate_to != role_id.lower():
            _publish_in_progress(
                stage="turn:delegated",
                kind=result_ref[0].kind,
            )

            return {
                "status": None,
                "token": None,
                "message": {
                    "type": "delegate",
                    "delegate_to": delegate_to,
                    "original_role": role_id,
                },
                "role": {
                    "role_id": delegate_to,
                    "name": delegate_to,
                },
                "error": None,
            }

    # merged_graph = await merge_latest_graph_for_final_output(
    #     graph_ref=graph_ref,
    #     initial_graph_md5=initial_graph_md5,
    # )
    #
    # if merged_graph is not None:
    #     graph_ref[0] = merged_graph

    content = content_ref[0]
    result = result_ref[0]
    workflow_response = response_ref[0]
    follow_up_contexts = follow_up_contexts_ref[0]
    apply_meta = apply_meta_ref[0]

    if workflow_response is not None:
        raw_run_output = getattr(
            workflow_response,
            "run_output",
            None,
        )

        if isinstance(raw_run_output, dict):
            run_output = raw_run_output

        llm_user_message = getattr(
            workflow_response,
            "llm_user_message",
            None,
        )
        llm_system_prompt = getattr(
            workflow_response,
            "llm_system_prompt",
            None,
        )
    else:
        llm_user_message = None
        llm_system_prompt = None

    graph_json = graph_to_json_object(graph_ref[0])

    display_content = str(
        result.content_for_display or content,
    ).strip()

    if not display_content:
        display_content = "(No response from role handler.)"

    final_message: Data = {
        "id": new_id(),
        "ts": now_ts(),
        "role": "agent",
        "content": display_content,
        "agent": agent_label,
        "turn_id": turn_id,
        "source": "agent_response",
        "workflow_response": {
            "reply": display_content,
            "result_kind": result_ref[0].kind,
        },
        "parsed_edits": to_json_value(result.edits),
        "apply": apply_meta,
        "graph": graph_json,
        "run_output": run_output,
        "follow_up_contexts": follow_up_contexts,
        "last_apply_result": to_json_value(last_apply_result_ref[0]),
        "session_language": session.session_language,
        "messenger": messenger,
        "llm_user_message": llm_user_message,
        "llm_system_prompt": llm_system_prompt,
    }

    if error_ref[0] is not None:
        final_message["error"] = error_ref[0]

    _publish_in_progress(
        stage="turn:completed",
        kind=result_ref[0].kind,
    )

    out = {
        "status": None,
        "token": {"type": "token", "token": display_content},
        "message": {"type": "final", "message": final_message},
        "role": {"role_id": role_id, "name": agent_label},
        "error": error_ref[0],
    }

    return out
