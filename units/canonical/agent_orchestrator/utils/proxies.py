import asyncio
from pathlib import Path
from typing import Any, Callable


class _SessionProxy:
    """
    Minimal session state object satisfying the _SessionLanguageSink protocol
    from gui.chat.context.language_control.
    Also carries chat history for format_previous_turn.
    """

    def __init__(self, session_language: str = "", history: list | None = None) -> None:
        self.session_language: str = session_language
        self.history: list[Any] = history or []


class _ToolCtxProxy:
    """
    Duck-typing context proxy for follow-up tool runners.

    Satisfies every attribute accessed by the built-in tool runner set
    (grep, rag_search, web_search, browse, github, report, read_file,
    read_code_block, read_current_workflow, add_comment, todo_manager,
    formulas_calc, run_workflow).
    """

    def __init__(
        self,
        *,
        graph_ref: list[Any],
        last_apply_result_ref: list[Any],
        follow_up_contexts: list[str],
        wf_language_hint: list[str],
        overrides: dict[str, Any],
        follow_up_tool_ids: tuple[str, ...] | None,
        analyst_mode: bool,
        agent_role_id: str,
        agent_workflow_path: Path | None,
        state: _SessionProxy,
        stream_cb: Callable[[str], None] | None,
        recent_changes: str | None,
        turn_id: str,
        agent_label: str,
        max_rounds: int,
        ordered_follow_up_tools: tuple[tuple[str, str], ...] | None = None,
    ) -> None:
        self.graph_ref = graph_ref
        self.last_apply_result_ref = last_apply_result_ref
        self.follow_up_contexts = follow_up_contexts
        self.wf_language_hint = wf_language_hint
        self.overrides = overrides
        self.follow_up_tool_ids = follow_up_tool_ids
        self.analyst_mode = analyst_mode
        self.agent_role_id = agent_role_id
        self.agent_workflow_path = agent_workflow_path
        self.state = state
        self._stream_cb = stream_cb
        self._recent_changes = recent_changes
        self.turn_id = turn_id
        self.agent_label = agent_label
        self.max_rounds = max_rounds
        self.ordered_follow_up_tools = ordered_follow_up_tools
        # Headless: no Flet page
        self.page: Any = None
        self.record_llm_prompt_view: Any = None
        self.follow_up_source_response: dict[str, Any] | None = None
        # Unique token; is_current_run always returns True in headless mode
        self.token: object = object()
        self.stream_buffer_ref: list[str] = [""]

    # ── Protocol methods ──

    def is_current_run(self, t: Any) -> bool:  # noqa: ARG002
        return True

    def get_recent_changes(self) -> str | None:
        return self._recent_changes

    def get_runtime_for_prompts(self, graph: Any) -> str:
        from gui.chat.agent_workflow.helpers import get_runtime_for_prompts

        return get_runtime_for_prompts(graph)

    def format_previous_turn(self, history: list[Any]) -> str:
        from gui.chat.handlers.chat_turn_context import format_previous_turn

        return format_previous_turn(history)

    def normalize_user_message_for_workflow(self, text: str) -> str:
        from gui.chat.handlers.chat_turn_context import (
            normalize_user_message_for_workflow,
        )

        return normalize_user_message_for_workflow(text)

    def set_inline_status(self, msg: str | None) -> None:
        if self._stream_cb is not None:
            try:
                from runtime.stream_ui_signals import inline_status_stream_chunk

                self._stream_cb(inline_status_stream_chunk(msg))
            except Exception:
                pass

    def append_message(
        self,
        role: str,  # noqa: ARG002
        content: str,  # noqa: ARG002
        meta: Any = None,  # noqa: ARG002
    ) -> None:
        pass  # no-op in headless mode

    def prepare_stream_row(self) -> None:
        pass  # no-op in headless mode

    async def run_workflow_streaming(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        kwargs.pop("_run_token", None)
        workflow_path = kwargs.pop("workflow_path", None)
        stream_cb = self._stream_cb

        if workflow_path is not None:
            return await func(
                *args, workflow_path=workflow_path, stream_callback=stream_cb
            )
        return await func(*args, stream_callback=stream_cb)

    async def toast(self, msg: str) -> None:  # noqa: ARG002
        pass  # no-op in headless mode
