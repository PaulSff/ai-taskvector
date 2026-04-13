"""web_search follow-up: run web_search workflow and inject results."""
from __future__ import annotations

from typing import Any, Callable

from assistants.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from assistants.tools.web_search.follow_ups import (
    WEB_SEARCH_FOLLOW_UP_PREFIX,
    WEB_SEARCH_FOLLOW_UP_SUFFIX,
)
from assistants.tools.types import FollowUpContribution
from gui.chat.workflow_designer_handler import (
    WEB_SEARCH_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from units.web import register_web_units


async def run_web_search_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    try:
        ctx.set_inline_status("Searching web…")
    except Exception:
        pass
    hint = language_hint
    chunk_ws: str | None = None
    try:
        register_web_units()
        out, errs = run_workflow_with_errors(
            WEB_SEARCH_WORKFLOW_PATH,
            initial_inputs={"inject_query": {"data": po["web_search"]}},
            unit_param_overrides={"web_search": {"max_results": po.get("web_search_max_results", 10)}},
            format="dict",
        )
        if errs and ctx.is_current_run(ctx.token):
            await ctx.toast(f"Web search error: {errs[0][1][:120]}")
        res = (out.get("web_search") or {}).get("out") or ""
        if res.strip():
            chunk_ws = (
                WEB_SEARCH_FOLLOW_UP_PREFIX
                + res
                + WEB_SEARCH_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
    except Exception:
        pass
    if not chunk_ws:
        chunk_ws = (
            WEB_SEARCH_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + WEB_SEARCH_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        return FollowUpContribution(context_chunks=[chunk_ws], any_empty_tool=True)
    return FollowUpContribution(context_chunks=[chunk_ws], any_empty_tool=False)


__all__ = ["run_web_search_follow_up"]
