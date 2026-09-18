import logging
from collections.abc import Callable
from pathlib import Path

from agents.chat.agent_workflow.wf_response_schema import (
    AgentWorkflowResponse,
)
from agents.chat.role_turns.protocol import WorkflowRunner
from agents.chat.session.state import AgentChatHistory, ChatSessionState
from core.schemas.primitives import Data, WorkflowInputs
from core.schemas.process_graph import ProcessGraph
from runtime.executor import GraphStreamCallback

logger = logging.getLogger(__name__)

class SessionProxy(ChatSessionState):
    """
    Minimal session state object satisfying the SessionLanguageSink protocol
    from agents.chat.context.language_control.
    Also carries chat history for format_previous_turn.
    """

    def __init__(
        self,
        session_language: str = "",
        history: AgentChatHistory | None = None,
    ) -> None:
        self.session_language: str = session_language
        self.history: AgentChatHistory = history or []

        print(
            f"[SessionProxy] init session_language={session_language!r} history_len={len(self.history)}",
            flush=True,
        )


class TurnRuntimeProxy:
    """Headless runtime bindings for ``RoleChatTurnContext.from_context``."""

    def __init__(
        self,
        *,
        graph_ref: list[ProcessGraph],
        stream_callback: GraphStreamCallback | None,
        stream_buffer_ref: list[str],
        state: ChatSessionState,
        role_id: str,
        token: int = 0,
        recent_changes: str | None = None,
        apply_from_agent: Callable[[ProcessGraph], None] | None = None,
    ) -> None:
        self.graph_ref = graph_ref
        self._stream_cb = stream_callback
        self.stream_buffer_ref = stream_buffer_ref
        self._state = state
        self._role_id = role_id
        self._token = token
        self._recent_changes = recent_changes
        self._apply_from_agent = apply_from_agent

    def set_graph(self, graph: ProcessGraph) -> None:
        self.graph_ref[0] = graph

    def is_current_run(self, run_token: int) -> bool:
        return run_token == self._token

    def get_recent_changes(self) -> str | None:
        return self._recent_changes

    async def toast(self, message: str) -> None:
        logger.info("[orchestrator] toast: %s", message)

    def set_inline_status(self, message: str | None) -> None:
        if self._stream_cb is None:
            return

        try:
            from runtime.stream_ui_signals import inline_status_stream_chunk

            self._stream_cb(inline_status_stream_chunk(message))
        except (TypeError, ValueError, AttributeError):
            return

    def append_message(
        self,
        role: str,
        content: str,
        *,
        meta: Data | None = None,
        **kwargs: object,
    ) -> None:
        del kwargs

        from units.taskvector.agent_orchestrator.utils.ids import new_id
        from units.taskvector.agent_orchestrator.utils.time import now_ts

        msg: Data = {
            "id": new_id(),
            "ts": now_ts(),
            "role": role,
            "content": content,
        }

        if meta:
            msg.update(meta)

        self._state.history.append(msg)

    def persist_history_debounced(self) -> None:
        return

    def workflow_debug_log(self, message: str) -> None:
        logger.debug("[orchestrator] %s", message)

    async def run_workflow_streaming(
        self,
        func: WorkflowRunner,
        initial_inputs: WorkflowInputs | None = None,
        unit_param_overrides: WorkflowInputs | None = None,
        execution_timeout_s: float | None = None,
        *,
        _run_token: object | None = None,
        workflow_path: str | Path | None = None,
        role_id: str,
    ) -> AgentWorkflowResponse:
        del _run_token

        return await func(
            initial_inputs,
            unit_param_overrides,
            execution_timeout_s,
            stream_callback=self._stream_cb,
            workflow_path=workflow_path,
            role_id=role_id,
        )
