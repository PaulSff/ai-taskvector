"""Shared RAG auto-delegation run before an agent turn (optional app setting)."""

from __future__ import annotations

import asyncio
from typing import cast

from gui.components.settings import (
    get_auto_delegate_workflow_path,
    get_auto_delegation_is_allowed,
)
from runtime.run import run_workflow


async def try_run_auto_delegate_before_turn(
    delegate_request_ref: list[dict[str, object] | None] | None,
    user_message_for_workflow: str,
    *,
    current_role_id: str | None = None,
) -> bool:
    """
    Run the dispatcher workflow when automatic delegation is allowed.

    On success, assign delegate_request_ref[0] and return True.
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
                "inject_msg": {
                    "data": {
                        "user_message": user_message_for_workflow,
                    },
                },
            },
        )
    except (OSError, ValueError, RuntimeError, TypeError):
        return False

    delegate_req = ad_out.get("delegate_req")

    if not isinstance(delegate_req, dict):
        return False

    dr_data_obj = delegate_req.get("data")

    if not isinstance(dr_data_obj, dict):
        return False

    dr_data = cast(dict[str, object], dr_data_obj)

    ok = dr_data.get("ok") is True
    delegate_to = dr_data.get("delegate_to")

    if not ok or not isinstance(delegate_to, str) or not delegate_to.strip():
        return False

    target = delegate_to.strip()
    current_role = (current_role_id or "").strip()

    if current_role and target.casefold() == current_role.casefold():
        return False

    delegate_request_ref[0] = dr_data
    return True
