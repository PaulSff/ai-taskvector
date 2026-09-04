"""Shared bindings for one agents-chat turn (built in ``chat.py``, consumed by ``gui.chat.role_turns``)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import flet as ft

from agents.chat.agent_workflow.wf_response_schema import MergeResponse
from agents.chat.session.state import ChatSessionState
from core.schemas.graph_edit_api import AgentApplyWorkflowEditsResult
from core.schemas.primitives import Data
from core.schemas.process_graph import ProcessGraph

if TYPE_CHECKING:
    from agents.chat.role_turns.protocol import WorkflowStreamingRunner


@dataclass
class RoleChatTurnContext:
    """Narrow environment for ``RoleChatHandler.run_turn``."""

    page: ft.Page
    state: ChatSessionState
    graph_ref: list[ProcessGraph]
    token: int
    turn_id: str
    agent_display: str
    profile: str
    provider: str
    cfg: Data
    rag_index_dir: Path
    rag_embedding_model: str
    mydata_dir: Path
    coding_is_allowed: bool
    contribution_is_allowed: bool
    training_config_path: str | None
    apply_from_agent: Callable[[Any], None] | None
    set_graph: Callable[[Any], None]
    get_recent_changes: Callable[[], str | None] | None
    on_show_run_console: Callable[..., Any] | None
    last_apply_result_ref: list[AgentApplyWorkflowEditsResult]
    stream_buffer_ref: list[str]
    is_current_run: Callable[[int], bool]
    toast: Callable[[str], Awaitable[None]]
    set_inline_status: Callable[[str | None], None]
    clear_stream_row: Callable[[], None]
    prepare_stream_row: Callable[[], None]
    append_message: Callable[..., Any]
    replace_agent_message_row: Callable[..., Any]
    run_workflow_streaming: WorkflowStreamingRunner
    persist_history_debounced: Callable[[], None]
    workflow_debug_log: Callable[[str], None]
    # Dev: last role chat Prompt → LLM strings; kw_only so it can follow required workflow_debug_log (Python 3.10+).
    record_llm_prompt_view: Callable[[MergeResponse], None] | None = field(
        default=None,
        kw_only=True,
    )
    # Single-slot ref ``[payload|None]``; Analyst sets resolved ``delegate_request`` merge output for chat handoff.
    delegate_request_ref: list[Data | None] | None = field(
        default=None, kw_only=True
    )
