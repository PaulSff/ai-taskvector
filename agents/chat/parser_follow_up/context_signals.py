"""Context indicatiors"""

from agents.chat.context.wf_response_schema import (
    ResponseData,
)


def workflow_response_is_question(resp: ResponseData) -> bool:
    """True when the agent workflow classified the current reply as a user question."""
    result = resp.get("result") or {}
    value = result.get("is_question")

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}

    return False


def workflow_merge_response_apply_failed(resp: ResponseData) -> bool:
    result = resp.get("result", {})
    status = resp.get("status") or {}

    return (
        result.get("kind") == "apply_failed"
        or (
            status.get("attempted") is True
            and status.get("success") is False
        )
    )
