"""
edit_file follow-up: edit file via edit_file workflow.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agents.chat.agent_workflow import (
    EDIT_FILE_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.tools.edit_file.follow_ups import (
    EDIT_FILE_FOLLOW_UP_PREFIX,
    EDIT_FILE_FOLLOW_UP_SUFFIX,
)
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.types import FollowUpContribution

EXECUTION_TIMEOUT_S: float = 30


async def run_edit_file_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    try:
        ctx.set_inline_status("Editing file…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint
    chunk_br: str | None = None

    try:
        out, errs = await run_workflow_with_errors(
            EDIT_FILE_WORKFLOW_PATH,
            initial_inputs={"inject_payload": {"data": po["edit_file"]}},
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs and ctx.is_current_run(ctx.token):
            await ctx.toast(f"Edit file error: {errs[0][1][:120]}")

        edit_file_out = (out or {}).get("edit_file") or {}
        edit_file_data = (edit_file_out or {}).get("data") or {}
        edit_file_error_port = edit_file_out.get("error") or ""

        # Prefer explicit error from the tool payload, otherwise fall back to errs.
        if edit_file_error_port:
            chunk_br = (
                EDIT_FILE_FOLLOW_UP_PREFIX
                + edit_file_error_port
                + EDIT_FILE_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
        elif edit_file_data:
            chunk_br = (
                EDIT_FILE_FOLLOW_UP_PREFIX
                + str(edit_file_data)
                + EDIT_FILE_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
    except (AttributeError, TypeError, IndexError):
        pass

    if not chunk_br:
        chunk_br = (
            EDIT_FILE_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + EDIT_FILE_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        return FollowUpContribution(context_chunks=[chunk_br], any_empty_tool=True)

    return FollowUpContribution(context_chunks=[chunk_br], any_empty_tool=False)


__all__ = ["run_edit_file_follow_up"]
