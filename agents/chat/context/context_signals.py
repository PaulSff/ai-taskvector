"""Context indicatiors"""
from __future__ import annotations

from agents.chat.agent_workflow.wf_response_schema import AgentWorkflowResponse


def workflow_response_is_question(resp: AgentWorkflowResponse) -> bool:
    """Return whether the workflow classified the current reply as a user question."""
    value = resp.merged_response.is_question

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}

    return False


def workflow_merge_response_apply_failed(
    resp: AgentWorkflowResponse,
) -> bool:
    merge_response = resp.merged_response
    result = merge_response.result
    status = merge_response.status

    result_failed = (
        result is not None
        and result.kind == "apply_failed"
    )

    status_failed = (
        status is not None
        and status.attempted is True
        and status.success is False
    )

    return result_failed or status_failed
