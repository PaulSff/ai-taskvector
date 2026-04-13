"""browse follow-up: fetch URL content via browser workflow."""
from __future__ import annotations

from typing import Any, Callable

from assistants.tools.browse.follow_ups import BROWSE_FOLLOW_UP_PREFIX, BROWSE_FOLLOW_UP_SUFFIX
from assistants.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from assistants.tools.types import FollowUpContribution
from gui.chat_with_the_assistants.workflow_designer_handler import (
    BROWSER_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from units.web import register_web_units


async def run_browse_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    try:
        ctx.set_inline_status("Loading page…")
    except Exception:
        pass
    hint = language_hint
    chunk_br: str | None = None
    try:
        register_web_units()
        out, errs = run_workflow_with_errors(
            BROWSER_WORKFLOW_PATH,
            initial_inputs={"inject_url": {"data": po["browse_url"]}},
            format="dict",
        )
        if errs and ctx.is_current_run(ctx.token):
            await ctx.toast(f"Browse error: {errs[0][1][:120]}")
        res = (out.get("beautifulsoup") or {}).get("out") or ""
        if res.strip():
            chunk_br = (
                BROWSE_FOLLOW_UP_PREFIX
                + res
                + BROWSE_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
    except Exception:
        pass
    if not chunk_br:
        chunk_br = (
            BROWSE_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + BROWSE_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        return FollowUpContribution(context_chunks=[chunk_br], any_empty_tool=True)
    return FollowUpContribution(context_chunks=[chunk_br], any_empty_tool=False)


__all__ = ["run_browse_follow_up"]
