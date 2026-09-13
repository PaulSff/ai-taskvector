from pathlib import Path

from agents.chat.context.follow_up_context import PostExecutionFollowUpContext
from agents.roles.types import RoleConfig
from agents.tools.catalog import ordered_tools_for_role_id
from core.schemas.graph_edit_api import AgentApplyWorkflowEditsResult
from core.schemas.process_graph import ProcessGraph
from units.taskvector.agent_orchestrator.utils.proxies import (
    SessionProxy,
    ToolCtxProxy,
)


def build_post_apply_context(
    *,
    session: SessionProxy,
    role_id: str,
    role_config: RoleConfig,
    turn_id: str,
    graph_ref: list[ProcessGraph],
    last_apply_result_ref: list[AgentApplyWorkflowEditsResult | None],
    wf_language_hint: list[str],
    recent_changes: str | None,
) -> PostExecutionFollowUpContext:
    overrides = role_config.chat_overrides or {}

    light_graph_mode = role_config.light_graph_mode

    agent_workflow_path = (
        Path(role_config.chat_workflow)
        if role_config.chat_workflow
        else None
    )

    max_rounds = (
        role_config.follow_up_max_rounds
        if role_config.follow_up_max_rounds is not None
        else 0
    )

    proxy = ToolCtxProxy(
        graph_ref=graph_ref,
        last_apply_result_ref=last_apply_result_ref,
        follow_up_contexts=[],
        wf_language_hint=wf_language_hint,
        overrides=overrides,
        follow_up_tool_ids=role_config.tools,
        light_graph_mode=light_graph_mode,
        agent_role_id=role_id,
        agent_workflow_path=agent_workflow_path,
        state=session,
        stream_cb=None,
        recent_changes=recent_changes,
        turn_id=turn_id,
        agent_label=role_id,
        max_rounds=max_rounds,
        ordered_follow_up_tools=ordered_tools_for_role_id(role_config.id),
        prefer_inline_workflow=True,
    )

    return PostExecutionFollowUpContext(
        graph_ref=graph_ref,
        state=session,
        token=proxy.token,
        turn_id=turn_id,
        agent_role_id=role_id,
        agent_label=role_id,
        max_rounds=max_rounds,
        wf_language_hint=wf_language_hint,
        is_current_run=proxy.is_current_run,
        toast=proxy.toast,
        set_inline_status=proxy.set_inline_status,
        append_message=proxy.append_message,
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
        stream_buffer_ref=[""],
        agent_workflow_path=agent_workflow_path,
        light_graph_mode=light_graph_mode,
    )
