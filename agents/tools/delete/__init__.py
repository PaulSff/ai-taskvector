"""
delete follow-up: delete file via delete workflow.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agents.chat.agent_workflow import (
    DELETE_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.tools.delete.follow_ups import (
    DELETE_FOLLOW_UP_PREFIX,
    DELETE_FOLLOW_UP_SUFFIX,
)
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.types import FollowUpContribution

EXECUTION_TIMEOUT_S: float = 30


async def run_delete_file_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    try:
        ctx.set_inline_status("Deleting items…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint
    chunk_br: str | None = None

    try:
        out, errs = await run_workflow_with_errors(
            DELETE_WORKFLOW_PATH,
            initial_inputs={"inject_payload": {"data": po["delete"]}},
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs and ctx.is_current_run(ctx.token):
            await ctx.toast(f"Delete file error: {errs[0][1][:120]}")

        delete_out = (out or {}).get("delete") or {}
        delete_data = (delete_out or {}).get("data") or {}
        delete_error_port = delete_out.get("error") or ""

        # Prefer explicit error from the tool payload, otherwise fall back to errs.
        if delete_error_port:
            chunk_br = (
                DELETE_FOLLOW_UP_PREFIX
                + delete_error_port
                + DELETE_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
        elif delete_data:
            chunk_br = (
                DELETE_FOLLOW_UP_PREFIX
                + str(delete_data)
                + DELETE_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
    except (AttributeError, TypeError, IndexError):
        pass

    if not chunk_br:
        chunk_br = (
            DELETE_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + DELETE_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        return FollowUpContribution(context_chunks=[chunk_br], any_empty_tool=True)

    return FollowUpContribution(context_chunks=[chunk_br], any_empty_tool=False)


__all__ = ["run_delete_file_follow_up"]
