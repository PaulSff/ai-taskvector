from pathlib import Path
from typing import Any, Callable, Literal

from gui.chat.agent_workflow.helpers import get_runtime_for_prompts


class _SessionProxy:
    """
    Minimal session state object satisfying the _SessionLanguageSink protocol
    from gui.chat.context.language_control.
    Also carries chat history for format_previous_turn.
    """

    def __init__(self, session_language: str = "", history: list | None = None) -> None:
        self.session_language: str = session_language
        self.history: list[Any] = history or []
        print(
            f"[SessionProxy] init session_language={session_language!r} history_len={len(self.history)}",
            flush=True,
        )


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
        prefer_inline_workflow: bool = False,
    ) -> None:
        print(
            "[ToolCtxProxy] init "
            f"analyst_mode={analyst_mode} agent_role_id={agent_role_id!r} agent_label={agent_label!r} "
            f"turn_id={turn_id!r} max_rounds={max_rounds} agent_workflow_path={agent_workflow_path!r} "
            f"follow_up_tool_ids={follow_up_tool_ids!r} prefer_inline_workflow={prefer_inline_workflow} "
            f"recent_changes={recent_changes!r}",
            flush=True,
        )

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
        self._prefer_inline_workflow = prefer_inline_workflow

        # Headless: no Flet page
        self.page: Any = None
        self.record_llm_prompt_view: Any = None
        self.follow_up_source_response: dict[str, Any] | None = None

        # Unique token; is_current_run always returns True in headless mode
        self.token: object = object()
        self.stream_buffer_ref: list[str] = [""]

        print(
            "[ToolCtxProxy] initialized "
            f"has_stream_cb={self._stream_cb is not None} "
            f"follow_up_contexts_len={len(self.follow_up_contexts)} "
            f"wf_language_hint_len={len(self.wf_language_hint)} "
            f"overrides_keys={len(self.overrides)} "
            f"ordered_follow_up_tools={self.ordered_follow_up_tools!r}",
            flush=True,
        )

    # ── Protocol methods ──

    def is_current_run(self, t: Any) -> bool:  # noqa: ARG002
        print("[ToolCtxProxy] is_current_run called (headless): always True", flush=True)
        return True

    def get_recent_changes(self) -> str | None:
        print(f"[ToolCtxProxy] get_recent_changes -> {self._recent_changes!r}", flush=True)
        return self._recent_changes

    async def get_runtime_for_prompts(self, graph: Any) -> Literal["native", "external"]:
        print("[ToolCtxProxy] get_runtime_for_prompts called", flush=True)
        rt = await get_runtime_for_prompts(graph)
        print(f"[ToolCtxProxy] get_runtime_for_prompts result -> {rt!r}", flush=True)
        return rt

    async def format_previous_turn(self, history: list[Any]) -> str:
        from gui.chat.handlers.chat_turn_context import format_previous_turn

        print(
            f"[ToolCtxProxy] format_previous_turn called history_len={len(history)} "
            f"history_type={type(history).__name__}",
            flush=True,
        )
        out = await format_previous_turn(history)
        print(
            f"[ToolCtxProxy] format_previous_turn done out_len={len(out)} out_type={type(out).__name__}",
            flush=True,
        )
        return out

    def normalize_user_message_for_workflow(self, text: str) -> str:
        from gui.chat.handlers.chat_turn_context import normalize_user_message_for_workflow

        print(
            f"[ToolCtxProxy] normalize_user_message_for_workflow called text_len={len(text)} "
            f"text_type={type(text).__name__}",
            flush=True,
        )
        out = normalize_user_message_for_workflow(text)
        print(
            f"[ToolCtxProxy] normalize_user_message_for_workflow done out_len={len(out)} out_type={type(out).__name__}",
            flush=True,
        )
        return out

    def set_inline_status(self, msg: str | None) -> None:
        print(
            f"[ToolCtxProxy] set_inline_status called msg={msg!r} has_stream_cb={self._stream_cb is not None}",
            flush=True,
        )
        if self._stream_cb is not None:
            try:
                from runtime.stream_ui_signals import inline_status_stream_chunk

                chunk = inline_status_stream_chunk(msg)
                print(
                    f"[ToolCtxProxy] set_inline_status sending chunk type={type(chunk).__name__}",
                    flush=True,
                )
                self._stream_cb(chunk)
            except Exception as e:
                print(f"[ToolCtxProxy] set_inline_status failed: {e!r}", flush=True)

    def append_message(self, role: str, content: str, meta: Any = None) -> None:
        print(
            "[ToolCtxProxy] append_message called (headless no-op) "
            f"role={role!r} content_len={len(content)} meta_type={type(meta).__name__}",
            flush=True,
        )
        return None

    def prepare_stream_row(self) -> None:
        print("[ToolCtxProxy] prepare_stream_row called (headless no-op)", flush=True)
        return None

    async def run_workflow_streaming(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        import asyncio

        print(
            "[ToolCtxProxy] DEBUG: run_workflow_streaming ENTER "
            f"func={getattr(func, '__name__', str(func))} args_len={len(args)} "
            f"kwargs_keys={list(kwargs.keys())} prefer_inline={self._prefer_inline_workflow}",
            flush=True,
        )

        kwargs.pop("_run_token", None)
        workflow_path = kwargs.pop("workflow_path", None)
        stream_cb = self._stream_cb

        print(
            "[ToolCtxProxy] run_workflow_streaming resolved "
            f"workflow_path={workflow_path!r} has_stream_cb={stream_cb is not None}",
            flush=True,
        )

        if self._prefer_inline_workflow and workflow_path is not None:
            from gui.chat.agent_workflow.run import merge_response_from_workflow_outputs
            from runtime.run import run_workflow

            initial_inputs = args[0] if args else {}
            unit_param_overrides = args[1] if len(args) > 1 else None
            execution_timeout_s = args[2] if len(args) > 2 else None

            print(
                "[ToolCtxProxy] Inline branch: "
                f"workflow_path={workflow_path!r} "
                f"initial_inputs_type={type(initial_inputs).__name__} "
                f"unit_param_overrides_type={type(unit_param_overrides).__name__} "
                f"execution_timeout_s={execution_timeout_s!r}",
                flush=True,
            )

            outputs = await asyncio.to_thread(
                run_workflow,
                workflow_path,
                initial_inputs=initial_inputs,
                unit_param_overrides=unit_param_overrides,
                format="dict",
                execution_timeout_s=execution_timeout_s,
                stream_callback=stream_cb,
            )

            print(
                f"[ToolCtxProxy] Inline run_workflow completed outputs_type={type(outputs).__name__}",
                flush=True,
            )

            merged = merge_response_from_workflow_outputs(outputs)
            print(
                f"[ToolCtxProxy] merge_response_from_workflow_outputs completed merged_type={type(merged).__name__}",
                flush=True,
            )
            return merged

        if workflow_path is not None:
            print("[ToolCtxProxy] Delegating to func with workflow_path", flush=True)
            out = await func(*args, workflow_path=workflow_path, stream_callback=stream_cb)
            print(
                f"[ToolCtxProxy] Delegated func completed out_type={type(out).__name__}",
                flush=True,
            )
            return out

        print("[ToolCtxProxy] Delegating to func without workflow_path", flush=True)
        out = await func(*args, stream_callback=stream_cb)
        print(
            f"[ToolCtxProxy] Delegated func completed out_type={type(out).__name__}",
            flush=True,
        )
        return out

    async def toast(self, msg: str) -> None:  # noqa: ARG002
        print(f"[ToolCtxProxy] toast (headless no-op): {msg!r}", flush=True)
        return None
