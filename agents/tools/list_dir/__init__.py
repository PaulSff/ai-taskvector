"""
browse follow-up: list directory via list_dir workflow.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agents.chat.agent_workflow import (
    LIST_DIR_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.list_dir.follow_ups import (
    LIST_DIR_FOLLOW_UP_PREFIX,
    LIST_DIR_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import (
    FOLLOW_UP_EXTRA_LIST_DIR_FOLLOW_UP,
    FollowUpContribution,
)

EXECUTION_TIMEOUT_S: float = 30


async def run_list_dir_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    try:
        ctx.set_inline_status("Inspecting the folder…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint
    chunk_br: str | None = None

    try:
        out, errs = await run_workflow_with_errors(
            LIST_DIR_WORKFLOW_PATH,
            initial_inputs={"inject_payload": {"data": po["list_dir"]}},
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs and ctx.is_current_run(ctx.token):
            await ctx.toast(f"List dir error: {errs[0][1][:120]}")

        list_dir_out = (out or {}).get("list_dir") or {}
        list_dir_data = (list_dir_out or {}).get("data") or {}
        list_dir_error_port = list_dir_out.get("error") or ""

        # Prefer explicit error from the tool payload, otherwise fall back to errs.
        if list_dir_error_port:
            chunk_br = (
                LIST_DIR_FOLLOW_UP_PREFIX
                + list_dir_error_port
                + LIST_DIR_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
        elif list_dir_data:
            # Assume list_dir_data is already a printable string or can be cast to one.
            chunk_br = (
                LIST_DIR_FOLLOW_UP_PREFIX
                + str(list_dir_data)
                + LIST_DIR_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
    except (AttributeError, TypeError, IndexError):
        pass

    if not chunk_br:
        chunk_br = (
            LIST_DIR_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + LIST_DIR_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        return FollowUpContribution(
            context_chunks=[chunk_br],
            any_empty_tool=True,
            extra={FOLLOW_UP_EXTRA_LIST_DIR_FOLLOW_UP: True},
        )

    return FollowUpContribution(
        context_chunks=[chunk_br],
        any_empty_tool=False,
        extra={FOLLOW_UP_EXTRA_LIST_DIR_FOLLOW_UP: True},
    )


__all__ = ["run_list_dir_follow_up"]
