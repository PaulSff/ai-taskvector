from typing import Any


def _build_initial_inputs(
    user_message: str,
    graph: Any,
    last_apply_result: Any,
    recent_changes: str | None,
    session_language: str,
    history: list[Any],
    wf_language_hint: str,
    *,
    follow_up_context: str = "",
    coding_is_allowed: bool = True,
    contribution_is_allowed: bool = False,
    analyst_mode: bool = False,
) -> dict[str, dict[str, Any]]:
    """Build initial_inputs for run_agent_workflow (workflow JSON injects)."""
    from agents.roles.workflow_designer.workflow_inputs import (
        build_agent_workflow_initial_inputs,
    )
    from gui.chat.agent_workflow.helpers import get_runtime_for_prompts
    from gui.chat.handlers.chat_turn_context import format_previous_turn

    runtime = get_runtime_for_prompts(graph)
    previous_turn = format_previous_turn(history)

    return build_agent_workflow_initial_inputs(
        user_message,
        graph,
        last_apply_result,
        recent_changes,
        follow_up_context,
        runtime=runtime,
        coding_is_allowed=coding_is_allowed,
        contribution_is_allowed=contribution_is_allowed,
        previous_turn=previous_turn,
        language_hint=wf_language_hint,
        session_language=session_language,
        analyst_mode=analyst_mode,
    )
