"""github follow-up: GitHub API workflow result."""
from __future__ import annotations

import json
from typing import Any, Callable

from assistants.skills.follow_up_common import TOOL_EMPTY_RESULT_LINE
from assistants.skills.github.follow_ups import GITHUB_FOLLOW_UP_PREFIX, GITHUB_FOLLOW_UP_SUFFIX
from assistants.skills.types import FollowUpContribution
from gui.flet.chat_with_the_assistants.workflow_designer_handler import (
    GITHUB_GET_WORKFLOW_PATH,
    run_workflow_with_errors,
)


async def run_github_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    try:
        ctx.set_inline_status("Querying GitHub…")
    except Exception:
        pass
    hint = language_hint
    chunk_gh: str | None = None
    try:
        out, errs = run_workflow_with_errors(
            GITHUB_GET_WORKFLOW_PATH,
            initial_inputs={"inject_action": {"data": po["github"]}},
            format="dict",
        )
        if errs and ctx.is_current_run(ctx.token):
            await ctx.toast(f"GitHub error: {errs[0][1][:120]}")
        gh_out = out.get("github_get") or {}
        data = gh_out.get("data")
        err_msg = gh_out.get("error")
        if err_msg:
            res = f"Error: {err_msg}"
        elif data is not None:
            try:
                res = json.dumps(data, indent=2, ensure_ascii=False)
            except Exception:
                res = str(data)
            if len(res) > 8000:
                res = res[:8000] + "\n... (truncated)"
        else:
            res = ""
        if res.strip():
            chunk_gh = (
                GITHUB_FOLLOW_UP_PREFIX
                + res
                + GITHUB_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
    except Exception:
        pass
    if not chunk_gh:
        chunk_gh = (
            GITHUB_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + GITHUB_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        return FollowUpContribution(context_chunks=[chunk_gh], any_empty_tool=True)
    return FollowUpContribution(context_chunks=[chunk_gh], any_empty_tool=False)


__all__ = ["run_github_follow_up"]
