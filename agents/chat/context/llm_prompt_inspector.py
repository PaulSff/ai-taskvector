"""
Dev inspector: extract system_prompt / user_message from role chat workflow outputs.

Role workflows conventionally use a ``Prompt`` unit (often id ``prompt_llm``) before ``LLMAgent``.
``attach_llm_prompt_debug_from_outputs`` copies those strings onto the response dict the GUI consumes;
``record_llm_prompt_view_if_present`` forwards them to the dev tab hook when present.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from agents.chat.agent_workflow.wf_response_schema import (
    AgentWorkflowResponse,
    MergeResponse,
)
from core.schemas.primitives import Data, WorkflowOutputs

# Common Prompt unit ids in agents/roles/*/…_workflow.json graphs.
_DEFAULT_PROMPT_UNIT_IDS: tuple[str, ...] = ("prompt_llm", "prompt")


def attach_llm_prompt_debug_from_outputs(
    outputs: WorkflowOutputs,
    data: Data,
    *,
    prompt_unit_ids: tuple[str, ...] = _DEFAULT_PROMPT_UNIT_IDS,
) -> None:
    """Merge Prompt unit outputs into ``data`` as
    ``llm_system_prompt`` / ``llm_user_message``.
    """
    for uid in prompt_unit_ids:
        pl = outputs.get(uid)

        if not isinstance(pl, dict):
            continue

        prompt_output = cast(dict[str, object], pl)

        sp = prompt_output.get("system_prompt")
        um = prompt_output.get("user_message")

        if isinstance(sp, str):
            data["llm_system_prompt"] = sp

        if isinstance(um, str):
            data["llm_user_message"] = um

        if isinstance(sp, str) or isinstance(um, str):
            return

def record_llm_prompt_view_if_present(
    response: AgentWorkflowResponse,
    hook: Callable[[MergeResponse], None] | None,
) -> None:
    """Invoke ``hook`` when the merged response includes LLM prompt fields."""
    if hook is None:
        return

    merged_response = response.merged_response

    if (
        merged_response.llm_system_prompt is None
        and merged_response.llm_user_message is None
    ):
        return

    hook(merged_response)
