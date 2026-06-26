from __future__ import annotations

from typing import Any, Callable

from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.types import FollowUpContribution
from agents.tools.web_search.follow_ups import (
    WEB_SEARCH_FOLLOW_UP_PREFIX,
    WEB_SEARCH_FOLLOW_UP_SUFFIX,
)
from gui.chat.agent_workflow import (
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

        q = po.get("web_search", "")
        if isinstance(q, (list, tuple)):
            q = " ".join(map(str, q))
        q = "" if q is None else str(q).strip()

        try:
            max_results = int(po.get("web_search_max_results", 10) or 10)
        except Exception:
            max_results = 10
        max_results = max(1, min(max_results, 20))

        initial_inputs = {"inject_query": {"data": q}}
        unit_param_overrides = {
            "web_search": {"safesearch": "off", "max_results": max_results}
        }

        print(
            f"[run_web_search_follow_up] calling run_workflow_with_errors q='{q[:80]}' max_results={max_results}"
        )

        out, errs = await run_workflow_with_errors(
            WEB_SEARCH_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format="dict",
        )

        print(
            f"[run_web_search_follow_up] run_workflow_with_errors returned errs_len={len(errs)} out_keys={list((out or {}).keys())}"
        )

        if errs:
            try:
                await ctx.toast(f"Web search error: {errs[0][1][:120]}")
            except Exception:
                pass

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

    except Exception as e:
        # don't swallow; make the failure visible to your chain
        try:
            await ctx.toast(
                f"Web search workflow crashed: {type(e).__name__}: {str(e)[:120]}"
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
