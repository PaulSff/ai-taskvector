from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agents.chat.agent_workflow import (
    CLONE_ROLE_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.tools.clone_role.follow_ups import (
    CLONE_ROLE_FOLLOW_UP_PREFIX,
    CLONE_ROLE_FOLLOW_UP_SUFFIX,
)
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.types import (
    FOLLOW_UP_EXTRA_CLONE_ROLE_FOLLOW_UP,
    FollowUpContribution,
)

EXECUTION_TIMEOUT_S: float = 60


async def run_clone_role_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    hint: Callable[[], str] = language_hint  # ensure always defined

    chunk_ws: str = ""

    try:
        try:
            ctx.set_inline_status("Cloning the Analyst…")
        except (AttributeError, TypeError):
            pass

        action_obj = po["clone_role"]  # required:
        # expected shape depends on clone_role workflow:
        # { "action": "clone_role", ... }

        initial_inputs = {"inject_action": {"template": action_obj}}

        out, errs = await run_workflow_with_errors(
            CLONE_ROLE_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            unit_param_overrides=None,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs:
            try:
                print("clone_role_follow_up: first error", errs[0])
            except (IndexError, TypeError):
                pass

        if errs:
            try:
                await ctx.toast(f"Clone role error: {errs[0][1][:120]}")
            except (AttributeError, TypeError, IndexError):
                pass

        # Try common output shapes; adjust if your workflow uses different ports.
        out_dict = out or {}
        clone_out = out_dict.get("clone_role") or out_dict
        data = {}

        if isinstance(clone_out, dict):
            # prefer nested data if present
            data = clone_out.get("data", clone_out)
        else:
            data = clone_out

        res = ""
        if isinstance(data, dict):
            if data.get("ok") is True:
                res = str(data)
            else:
                res = str(
                    data.get("error") or data.get("message") or ""
                )
        else:
            res = str(data or "")

        if res.strip():
            chunk_ws = (
                CLONE_ROLE_FOLLOW_UP_PREFIX
                + res
                + CLONE_ROLE_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )

    except (KeyError, TypeError, ValueError) as e:
        print(
            "clone_role_follow_up: crashed",
            {"type": type(e).__name__, "message": str(e)[:300]},
        )
        try:
            await ctx.toast(
                f"Clone role workflow crashed: {type(e).__name__}: {str(e)[:120]}"
            )
        except (AttributeError, TypeError):
            pass
        chunk_ws = ""

    if not chunk_ws:
        chunk_ws = (
            CLONE_ROLE_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + CLONE_ROLE_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        print("clone_role_follow_up: returning empty tool result")
        return FollowUpContribution(
            context_chunks=[chunk_ws],
            any_empty_tool=True,
            extra={FOLLOW_UP_EXTRA_CLONE_ROLE_FOLLOW_UP: True},
        )

    print("clone_role_follow_up: returning non-empty context chunk")
    return FollowUpContribution(
        context_chunks=[chunk_ws],
        any_empty_tool=False,
        extra={FOLLOW_UP_EXTRA_CLONE_ROLE_FOLLOW_UP: True},
    )


__all__ = ["run_clone_role_follow_up"]
