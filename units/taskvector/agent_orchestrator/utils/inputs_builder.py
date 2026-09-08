from __future__ import annotations

from agents.chat.session.state import AgentChatHistory
from core.schemas import ProcessGraph
from core.schemas.graph_edit_api import AgentApplyWorkflowEditsResult
from core.schemas.primitives import WorkflowInputs


async def build_initial_inputs(
    user_message: str,
    graph: ProcessGraph,
    last_apply_result: AgentApplyWorkflowEditsResult | None,
    recent_changes: str | None,
    session_language: str,
    history: AgentChatHistory,
    wf_language_hint: str,
    *,
    follow_up_context: str = "",
    coding_is_allowed: bool = True,
    contribution_is_allowed: bool = False,
    light_graph_mode: bool = False,
) -> WorkflowInputs:
    """Build initial_inputs for run_agent_workflow (workflow JSON injects)."""
    from agents.chat.agent_workflow.helpers import get_runtime_for_prompts
    from agents.chat.handlers.chat_turn_context import format_previous_turn
    from agents.roles.workflow_designer.workflow_inputs import (
        build_agent_workflow_initial_inputs,
    )

    runtime = await get_runtime_for_prompts(graph)
    previous_turn = await format_previous_turn(history)

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
        light_graph_mode=light_graph_mode,
    )
