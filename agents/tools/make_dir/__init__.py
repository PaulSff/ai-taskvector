"""
make_dir follow-up: make directory via make_dir workflow.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agents.chat.agent_workflow import (
    MAKE_DIR_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.make_dir.follow_ups import (
    MAKE_DIR_FOLLOW_UP_PREFIX,
    MAKE_DIR_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import FollowUpContribution

EXECUTION_TIMEOUT_S: float = 30


async def run_make_dir_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    try:
        ctx.set_inline_status("Creating new folder…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint
    chunk_br: str | None = None

    try:
        out, errs = await run_workflow_with_errors(
            MAKE_DIR_WORKFLOW_PATH,
            initial_inputs={"inject_payload": {"data": po["make_dir"]}},
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs and ctx.is_current_run(ctx.token):
            await ctx.toast(f"Make dir error: {errs[0][1][:120]}")

        make_dir_out = (out or {}).get("make_dir") or {}
        make_dir_data = (make_dir_out or {}).get("data") or {}
        make_dir_error_port = make_dir_out.get("error") or ""

        if make_dir_error_port:
            chunk_br = (
                MAKE_DIR_FOLLOW_UP_PREFIX
                + make_dir_error_port
                + MAKE_DIR_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
        elif make_dir_data:
            chunk_br = (
                MAKE_DIR_FOLLOW_UP_PREFIX
                + str(make_dir_data)
                + MAKE_DIR_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
    except (AttributeError, TypeError, IndexError):
        pass

    if not chunk_br:
        chunk_br = (
            MAKE_DIR_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + MAKE_DIR_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        return FollowUpContribution(context_chunks=[chunk_br], any_empty_tool=True)

    return FollowUpContribution(context_chunks=[chunk_br], any_empty_tool=False)


__all__ = ["run_make_dir_follow_up"]
