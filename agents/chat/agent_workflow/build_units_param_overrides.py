from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from agents.roles.registry import get_role
from core.schemas.primitives import WorkflowInputs


def build_agent_workflow_unit_param_overrides(
    role_id: str,
) -> WorkflowInputs:
    """
    Build workflow-unit parameter overrides from ``chat.overrides``.

    Workflow units are discovered by looking for the ``template_path``
    parameter rather than by assuming a specific unit ID such as
    ``prompt_llm``.
    """
    role = get_role(role_id)

    overrides: WorkflowInputs = deepcopy(
        role.chat_overrides or {},
    )

    from agents.chat.handlers.prompt_delegate_tool_visibility import (
        merge_prompt_llm_strip_delegate_when_auto,
    )

    for unit_params in overrides.values():
        if not isinstance(unit_params, dict):
            continue

        template_path = unit_params.get("template_path")

        if not isinstance(template_path, str) or not template_path.strip():
            continue

        prompt_path = Path(template_path).resolve()
        unit_params["template_path"] = str(prompt_path)

        merge_prompt_llm_strip_delegate_when_auto(
            overrides,
            prompt_path,
        )

    return overrides
