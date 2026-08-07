"""
rename follow-up: rename item via rename workflow.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agents.chat.agent_workflow import (
    RENAME_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.rename.follow_ups import (
    RENAME_FOLLOW_UP_PREFIX,
    RENAME_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import FollowUpContribution

EXECUTION_TIMEOUT_S: float = 30


async def run_rename_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    try:
        ctx.set_inline_status("Renaming item…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint
    chunk_br: str | None = None

    try:
        out, errs = await run_workflow_with_errors(
            RENAME_WORKFLOW_PATH,
            initial_inputs={"inject_payload": {"data": po["rename"]}},
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs and ctx.is_current_run(ctx.token):
            await ctx.toast(f"Rename error: {errs[0][1][:120]}")

        rename_out = (out or {}).get("rename") or {}
        rename_data = (rename_out or {}).get("data") or {}
        rename_error_port = rename_out.get("error") or ""

        # Prefer explicit error from the tool payload, otherwise fall back to errs.
        if rename_error_port:
            chunk_br = (
                RENAME_FOLLOW_UP_PREFIX
                + rename_error_port
                + RENAME_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
        elif rename_data:
            chunk_br = (
                RENAME_FOLLOW_UP_PREFIX
                + str(rename_data)
                + RENAME_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
    except (AttributeError, TypeError, IndexError):
        pass

    if not chunk_br:
        chunk_br = (
            RENAME_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + RENAME_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        return FollowUpContribution(context_chunks=[chunk_br], any_empty_tool=True)

    return FollowUpContribution(context_chunks=[chunk_br], any_empty_tool=False)


__all__ = ["run_rename_follow_up"]
