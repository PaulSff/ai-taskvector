"""
browse follow-up: create new file via new_file workflow.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agents.chat.agent_workflow import (
    NEW_FILE_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.new_file.follow_ups import (
    NEW_FILE_FOLLOW_UP_PREFIX,
    NEW_FILE_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import FollowUpContribution

EXECUTION_TIMEOUT_S: float = 30


async def run_new_file_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    try:
        ctx.set_inline_status("Creating new file…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint
    chunk_br: str | None = None

    try:
        out, errs = await run_workflow_with_errors(
            NEW_FILE_WORKFLOW_PATH,
            initial_inputs={"inject_payload": {"data": po["new_file"]}},
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs and ctx.is_current_run(ctx.token):
            await ctx.toast(f"New file error: {errs[0][1][:120]}")

        new_file_out = (out or {}).get("generate_new_file") or {}
        new_file_data = (new_file_out or {}).get("data") or {}
        new_file_error_port = new_file_out.get("error") or ""

        # Prefer explicit error from the tool payload, otherwise fall back to errs.
        if new_file_error_port:
            chunk_br = (
                NEW_FILE_FOLLOW_UP_PREFIX
                + new_file_error_port
                + NEW_FILE_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
        elif new_file_data:
            chunk_br = (
                NEW_FILE_FOLLOW_UP_PREFIX
                + str(new_file_data)
                + NEW_FILE_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
    except (AttributeError, TypeError, IndexError):
        pass

    if not chunk_br:
        chunk_br = (
            NEW_FILE_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + NEW_FILE_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        return FollowUpContribution(context_chunks=[chunk_br], any_empty_tool=True)

    return FollowUpContribution(context_chunks=[chunk_br], any_empty_tool=False)


__all__ = ["run_new_file_follow_up"]
