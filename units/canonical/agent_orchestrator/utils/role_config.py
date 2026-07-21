from pathlib import Path
from typing import Any


def _get_role_config(role_id: str, ctx: dict[str, Any]) -> dict[str, Any]:
    """
    Build role execution config: workflow_path, overrides, analyst_mode, tool lists,
    max_follow_ups.
    """
    from agents.roles.registry import get_role
    from agents.roles.workflow_path import get_role_chat_workflow_path
    from agents.tools.catalog import (
        _ordered_tools_for_role_id,
    )
    from gui.chat.agent_workflow.helpers import build_agent_workflow_unit_param_overrides
    from gui.components.settings import get_workflow_designer_max_follow_ups

    role = get_role(role_id)

    # analyst_mode=True for every role except workflow_designer
    analyst_mode = role.id != "workflow_designer"
    is_rl_coach = role.id == "rl_coach"

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

    ordered_tools = _ordered_tools_for_role_id(role_id)  # (tool_id, parser_key) pairs
    follow_up_tool_ids = tuple(tid for tid, _ in ordered_tools)

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
