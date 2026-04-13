"""Shared RAG auto-delegation run before an assistant turn (optional app setting)."""
from __future__ import annotations

import asyncio
from typing import Any

from gui.components.settings import get_auto_delegate_workflow_path, get_auto_delegation_is_allowed
from runtime.run import run_workflow


async def try_run_auto_delegate_before_turn(
    delegate_request_ref: list[dict[str, Any] | None] | None,
    user_message_for_workflow: str,
) -> bool:
    """
    When settings allow and the workflow file exists, run ``auto_delegate_workflow.json``.
    On success, assign ``delegate_request_ref[0]`` and return True (caller should skip the main LLM turn).
    """
    if delegate_request_ref is None or not get_auto_delegation_is_allowed():
        return False
    ad_path = get_auto_delegate_workflow_path()
    if not ad_path.is_file():
        return False
    try:
        ad_out = await asyncio.to_thread(
            run_workflow,
            ad_path,
            initial_inputs={
                "inject_msg": {"data": {"user_message": user_message_for_workflow}},
            },
        )
    except Exception:
        return False
    dr_data = (ad_out or {}).get("delegate_req", {}).get("data")
    if (
        isinstance(dr_data, dict)
        and dr_data.get("ok") is True
        and (dr_data.get("delegate_to") or "").strip()
    ):
        delegate_request_ref[0] = dr_data
        return True
    return False
