from pathlib import Path
from typing import Any


def _get_role_config(role_id: str, ctx: dict[str, Any]) -> dict[str, Any]:
    """
    Build role execution config: workflow_path, overrides, analyst_mode, tool lists,
    max_follow_ups.
    """
    from agents.roles.registry import (
        ANALYST_ROLE_ID,
        RL_COACH_ROLE_ID,
        get_role,
    )
    from agents.roles.workflow_path import get_role_chat_workflow_path
    from agents.tools.catalog import (
        ORDERED_ANALYST_TOOLS,
        ORDERED_WORKFLOW_DESIGNER_TOOLS,
        analyst_tool_ids,
        workflow_designer_tool_ids,
    )
    from gui.chat.agent_workflow.helpers import (
        build_agent_workflow_unit_param_overrides,
    )
    from gui.components.settings import get_workflow_designer_max_follow_ups

    role = get_role(role_id)
    is_analyst = role_id == ANALYST_ROLE_ID
    is_rl_coach = role_id == RL_COACH_ROLE_ID
    analyst_mode = is_analyst or is_rl_coach

    workflow_path = get_role_chat_workflow_path(role_id)
    provider = str(ctx.get("provider") or "ollama")
    cfg = dict(ctx.get("cfg") or {})
    mydata_dir = str(ctx.get("mydata_dir") or ".")
    report_output_dir = str(Path(mydata_dir) / "reports")

    # Role-specific prompt template: config/prompts/<role_id>.json.
    # Without this, build_agent_workflow_unit_param_overrides falls back to the
    # WD prompt for every role, making analyst and rl_coach behave like WD.
    prompt_template_path: str | None = None
    try:
        from gui.components.settings import REPO_ROOT

        p = REPO_ROOT / "config" / "prompts" / f"{role_id}.json"
        if p.is_file():
            prompt_template_path = str(p)
    except Exception:
        pass

    overrides = build_agent_workflow_unit_param_overrides(
        provider,
        cfg,
        report_output_dir=report_output_dir,
        prompt_template_path=prompt_template_path,
        llm_options_role_id=role_id,
        rag_top_k_role_id=role_id,
    )

    max_follow_ups: int = (
        role.follow_up_max_rounds
        if role.follow_up_max_rounds is not None
        else get_workflow_designer_max_follow_ups()
    )

    if analyst_mode:
        ordered_tools: tuple[tuple[str, str], ...] = ORDERED_ANALYST_TOOLS
        follow_up_tool_ids: tuple[str, ...] | None = (
            role.tools if role.tools else tuple(analyst_tool_ids())
        )
    else:
        ordered_tools = ORDERED_WORKFLOW_DESIGNER_TOOLS
        follow_up_tool_ids = (
            role.tools if role.tools else tuple(workflow_designer_tool_ids())
        )

    return {
        "role_id": role_id,
        "workflow_path": workflow_path,
        "overrides": overrides,
        "analyst_mode": analyst_mode,
        "is_rl_coach": is_rl_coach,
        "max_follow_ups": max_follow_ups,
        "follow_up_tool_ids": follow_up_tool_ids,
        "ordered_follow_up_tools": ordered_tools,
    }
