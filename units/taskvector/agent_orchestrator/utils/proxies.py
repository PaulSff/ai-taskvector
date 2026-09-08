import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from agents.chat.agent_workflow.helpers import get_runtime_for_prompts
from agents.chat.agent_workflow.wf_response_schema import (
    AgentWorkflowResponse,
    MergeResponse,
)
from agents.chat.role_turns.protocol import WorkflowRunner
from agents.chat.session.state import AgentChatHistory, ChatSessionState
from agents.tools.catalog import OrderedToolsForRole
from agents.tools.types import ToolList
from core.schemas.graph_edit_api import AgentApplyWorkflowEditsResult
from core.schemas.primitives import Data, WorkflowInputs
from core.schemas.process_graph import ProcessGraph
from runtime.executor import GraphStreamCallback


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

class ToolCtxProxy:
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
        graph_ref: list[ProcessGraph],
        last_apply_result_ref: list[AgentApplyWorkflowEditsResult | None],
        follow_up_contexts: list[str],
        wf_language_hint: list[str],
        overrides: WorkflowInputs,
        follow_up_tool_ids: ToolList | None,
        light_graph_mode: bool,
        agent_role_id: str,
        agent_workflow_path: Path | None,
        state: SessionProxy,
        stream_cb: GraphStreamCallback| None,
        recent_changes: str | None,
        turn_id: str,
        agent_label: str,
        max_rounds: int,
        ordered_follow_up_tools: OrderedToolsForRole | None = None,
        prefer_inline_workflow: bool = False,
    ) -> None:
        print(
            "[ToolCtxProxy] init "
            + f"light_graph_mode={light_graph_mode} "
            + f"agent_role_id={agent_role_id!r} "
            + f"agent_label={agent_label!r} "
            + f"turn_id={turn_id!r} "
            + f"max_rounds={max_rounds} "
            + f"agent_workflow_path={agent_workflow_path!r} "
            + f"follow_up_tool_ids={follow_up_tool_ids!r} "
            + f"prefer_inline_workflow={prefer_inline_workflow} "
            + f"recent_changes={recent_changes!r}",
            flush=True,
        )

        self.graph_ref: list[ProcessGraph] = graph_ref
        self.last_apply_result_ref: list[
            AgentApplyWorkflowEditsResult | None
        ] = last_apply_result_ref
        self.follow_up_contexts: list[str] = follow_up_contexts
        self.wf_language_hint: list[str] = wf_language_hint
        self.overrides: WorkflowInputs = overrides
        self.follow_up_tool_ids: ToolList | None = follow_up_tool_ids
        self.light_graph_mode: bool = light_graph_mode
        self.agent_role_id: str = agent_role_id
        self.agent_workflow_path: Path | None = agent_workflow_path
        self.state: SessionProxy = state
        self._stream_cb: GraphStreamCallback | None = stream_cb
        self._recent_changes: str | None = recent_changes
        self.turn_id: str = turn_id
        self.agent_label: str = agent_label
        self.max_rounds: int = max_rounds
        self.ordered_follow_up_tools: OrderedToolsForRole | None = (
            ordered_follow_up_tools
        )
        self._prefer_inline_workflow: bool = prefer_inline_workflow


        # Headless:
        self.page: object = None
        self.record_llm_prompt_view: Callable[[MergeResponse], None] | None = None
        self.follow_up_source_response: Data | None = None

        # Unique token; is_current_run always returns True in headless mode
        self.token: int = time.monotonic_ns()
        self.stream_buffer_ref: list[str] = [""]

        print(
            "[ToolCtxProxy] initialized "
            + f"has_stream_cb={self._stream_cb is not None} "
            + f"follow_up_contexts_len={len(self.follow_up_contexts)} "
            + f"wf_language_hint_len={len(self.wf_language_hint)} "
            + f"overrides_keys={len(self.overrides)} "
            + f"ordered_follow_up_tools={self.ordered_follow_up_tools!r}",
            flush=True,
        )

    # ── Protocol methods ──

    def is_current_run(self, t: int) -> bool:
        print("[ToolCtxProxy] is_current_run called (headless): always True", flush=True)
        return True

    def get_recent_changes(self) -> str | None:
        print(f"[ToolCtxProxy] get_recent_changes -> {self._recent_changes!r}", flush=True)
        return self._recent_changes

    async def get_runtime_for_prompts(self, graph: ProcessGraph) -> Literal["native", "external"]:
        rt = await get_runtime_for_prompts(graph)
        print(f"[ToolCtxProxy] get_runtime_for_prompts result -> {rt!r}", flush=True)
        return rt

    async def format_previous_turn(self, history: AgentChatHistory) -> str:
        from agents.chat.handlers.chat_turn_context import format_previous_turn

        out = await format_previous_turn(history)
        print(
            f"[ToolCtxProxy] format_previous_turn done out_len={len(out)} out_type={type(out).__name__}",
            flush=True,
        )
        return out

    def normalize_user_message_for_workflow(self, text: str) -> str:
        from agents.chat.handlers.chat_turn_context import (
            normalize_user_message_for_workflow,
        )

        out = normalize_user_message_for_workflow(text)
        print(
            f"[ToolCtxProxy] normalize_user_message_for_workflow done out_len={len(out)} out_type={type(out).__name__}",
            flush=True,
        )
        return out

    def set_inline_status(self, msg: str | None) -> None:
        green = "\033[92m"  # 256-color green
        reset = "\033[0m"

        print(
            f"{green}[ToolCtxProxy] set_inline_status called msg={msg!r} has_stream_cb={self._stream_cb is not None}{reset}",
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
            except (TypeError, ValueError, AttributeError) as e:
                print(f"[ToolCtxProxy] set_inline_status failed: {e!r}", flush=True)

    def append_message(self, role: str, content: str, meta: Data) -> None:
        print(
            "[ToolCtxProxy] append_message called (headless no-op) "
            + f"role={role!r} content_len={len(content)} meta_type={type(meta).__name__}",
            flush=True,
        )

    def prepare_stream_row(self) -> None:
        print("[ToolCtxProxy] prepare_stream_row called (headless no-op)", flush=True)

    async def run_workflow_streaming(
        self,
        func: WorkflowRunner,
        initial_inputs: WorkflowInputs | None = None,
        unit_param_overrides: WorkflowInputs | None = None,
        execution_timeout_s: float | None = None,
        *,
        _run_token: object | None = None,
        workflow_path: str | Path | None = None,
    ) -> AgentWorkflowResponse:
        import asyncio

        del _run_token

        stream_cb = self._stream_cb

        if self._prefer_inline_workflow and workflow_path is not None:
            from agents.chat.agent_workflow.collect_workflow_response import (
                merge_response_from_workflow_outputs,
            )
            from runtime.run import run_workflow

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
                "[ToolCtxProxy] Inline run_workflow completed "
                + f"outputs_type={type(outputs).__name__}",
                flush=True,
            )

            merged = merge_response_from_workflow_outputs(outputs)

            print(
                "[ToolCtxProxy] merge_response_from_workflow_outputs completed "
                + f"merged_type={type(merged).__name__}",
                flush=True,
            )

            return merged

        return await func(
            initial_inputs,
            unit_param_overrides,
            execution_timeout_s,
            stream_callback=stream_cb,
            workflow_path=workflow_path,
        )

    async def toast(self, msg: str) -> None:
        orange = "\033[38;5;208m"   # 256-color orange
        reset = "\033[0m"
        print(f"{orange}[ToolCtxProxy] toast: {msg}{reset}", flush=True)
