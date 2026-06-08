from typing import Any

from gui.chat.parser_follow_up.chain import (
    PostApplyFollowUpContext,
)
from units.canonical.agent_orchestrator.utils.proxies import (
    _SessionProxy,
    _ToolCtxProxy,
)


def _build_post_apply_context(
    *,
    session: _SessionProxy,
    role_id: str,
    role_config: dict[str, Any],
    turn_id: str,
    graph_ref: list[Any],
    last_apply_result_ref: list[Any],
    wf_language_hint: list[str],
    recent_changes: str | None,
) -> PostApplyFollowUpContext:

    proxy = _ToolCtxProxy(
        graph_ref=graph_ref,
        last_apply_result_ref=last_apply_result_ref,
        follow_up_contexts=[],
        wf_language_hint=wf_language_hint,
        overrides=role_config["overrides"],
        follow_up_tool_ids=role_config["follow_up_tool_ids"],
        analyst_mode=role_config["analyst_mode"],
        agent_role_id=role_id,
        agent_workflow_path=role_config["workflow_path"],
        state=session,
        stream_cb=None,
        recent_changes=recent_changes,
        turn_id=turn_id,
        agent_label=role_id,
        max_rounds=role_config["max_follow_ups"],
        ordered_follow_up_tools=role_config["ordered_follow_up_tools"],
    )

    return PostApplyFollowUpContext(
        graph_ref=graph_ref,
        state=session,
        token=proxy.token,
        turn_id=turn_id,
        agent_role_id=role_id,
        agent_label=role_id,
        max_rounds=role_config["max_follow_ups"],
        wf_language_hint=wf_language_hint,
        is_current_run=proxy.is_current_run,
        toast=proxy.toast,
        set_inline_status=proxy.set_inline_status,
        append_message=proxy.append_message,
        prepare_stream_row=proxy.prepare_stream_row,
        normalize_user_message_for_workflow=proxy.normalize_user_message_for_workflow,
        last_apply_result_ref=last_apply_result_ref,
        get_recent_changes=proxy.get_recent_changes,
        overrides=role_config["overrides"],
        run_workflow_streaming=proxy.run_workflow_streaming,
        get_runtime_for_prompts=proxy.get_runtime_for_prompts,
        format_previous_turn=proxy.format_previous_turn,
        replace_agent_message_row=lambda _: None,
        stream_buffer_ref=[""],
        apply_fn=lambda g: graph_ref.__setitem__(0, g),
        agent_workflow_path=role_config["workflow_path"],
        analyst_mode=role_config["analyst_mode"],
    )
