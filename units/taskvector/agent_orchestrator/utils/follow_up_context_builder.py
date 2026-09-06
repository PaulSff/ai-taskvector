from __future__ import annotations

from pathlib import Path

from agents.chat.context.follow_up_context import (
    ExecutionFollowUpContext,
)
from agents.chat.session.state import AgentChatHistory
from agents.roles.types import RoleConfig
from agents.tools.catalog import ordered_tools_for_role_id
from core.schemas.graph_edit_api import AgentApplyWorkflowEditsResult
from core.schemas.process_graph import ProcessGraph
from runtime.executor import GraphStreamCallback
from units.taskvector.agent_orchestrator.utils.proxies import (
    SessionProxy,
    ToolCtxProxy,
)


def build_parser_follow_up_context(
    *,
    session: SessionProxy,
    role_id: str,
    role_config: RoleConfig,
    history: AgentChatHistory,
    turn_id: str,
    agent_display: str,
    follow_up_contexts: list[str],
    stream_cb: GraphStreamCallback | None,
    graph_ref: list[ProcessGraph],
    last_apply_result_ref: list[AgentApplyWorkflowEditsResult | None],
    wf_language_hint: list[str],
    recent_changes: str | None,
) -> ExecutionFollowUpContext:
    overrides = role_config.chat_overrides or {}

    agent_workflow_path = (
        Path(role_config.chat_workflow)
        if role_config.chat_workflow
        else None
    )

    analyst_mode = role_config.analyst_mode

    max_rounds = (
        role_config.follow_up_max_rounds
        if role_config.follow_up_max_rounds is not None
        else 0
    )

    ordered_follow_up_tools = ordered_tools_for_role_id(role_config.id)

    proxy = ToolCtxProxy(
        graph_ref=graph_ref,
        last_apply_result_ref=last_apply_result_ref,
        follow_up_contexts=follow_up_contexts,
        wf_language_hint=wf_language_hint,
        overrides=overrides,
        follow_up_tool_ids=role_config.tools,
        analyst_mode=analyst_mode,
        agent_role_id=role_id,
        agent_workflow_path=agent_workflow_path,
        state=session,
        stream_cb=stream_cb,
        recent_changes=recent_changes,
        turn_id=turn_id,
        agent_label=agent_display,
        max_rounds=max_rounds,
        ordered_follow_up_tools=ordered_follow_up_tools,
    )

    return ExecutionFollowUpContext(
        page=None,
        graph_ref=graph_ref,
        state=session,
        token=proxy.token,
        turn_id=turn_id,
        agent_label=agent_display,
        follow_up_contexts=follow_up_contexts,
        max_rounds=max_rounds,
        wf_language_hint=wf_language_hint,
        is_current_run=proxy.is_current_run,
        toast=proxy.toast,
        set_inline_status=proxy.set_inline_status,
        append_message=proxy.append_message,
        prepare_stream_row=proxy.prepare_stream_row,
        normalize_user_message_for_workflow=(
            proxy.normalize_user_message_for_workflow
        ),
        last_apply_result_ref=last_apply_result_ref,
        get_recent_changes=proxy.get_recent_changes,
        overrides=overrides,
        run_workflow_streaming=proxy.run_workflow_streaming,
        get_runtime_for_prompts=(
            lambda graph: proxy.get_runtime_for_prompts(
                graph if graph is not None else graph_ref[0]
            )
        ),
        format_previous_turn=proxy.format_previous_turn,
        follow_up_tool_ids=role_config.tools,
        agent_role_id=role_id,
        agent_workflow_path=agent_workflow_path,
        analyst_mode=analyst_mode,
        ordered_follow_up_tools=ordered_follow_up_tools,
    )
