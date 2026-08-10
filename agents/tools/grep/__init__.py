from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agents.chat.agent_workflow import (
    GREP_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.grep.follow_ups import (
    GREP_FOLLOW_UP_PREFIX,
    GREP_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import FollowUpContribution

EXECUTION_TIMEOUT_S: float = 60.0


async def run_grep_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    try:
        setter = getattr(ctx, "set_inline_status", None)
        if callable(setter):
            setter("Using grep…")
    except (TypeError, RuntimeError):
        pass

    hint = language_hint
    chunk_ws: str | None = None

    try:
        action_obj = po["grep"]  # required:
        # { "action": "grep", "grep": { "pattern": ..., "source": ... } }

        initial_inputs = {"inject_payload": {"data": action_obj}}

        out, errs = await run_workflow_with_errors(
            GREP_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            unit_param_overrides=None,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs:
            try:
                await ctx.toast(f"Grep error: {errs[0][1][:120]}")
            except (AttributeError, TypeError, IndexError):
                pass

        # Grep result extraction
        grep_out = (out or {}).get("grep") or {}
        grep_output = grep_out.get("out")
        grep_error_port = grep_out.get("error") or ""

        # Normalize result to string body
        res = ""
        if grep_output is None:
            res = ""
        else:
            res = str(grep_output).strip()

        if grep_error_port and grep_error_port.strip():
            if res:
                res = f"{res}\nError: {grep_error_port}".strip()
            else:
                res = f"Error: {grep_error_port}".strip()

        if res.strip():
            chunk_ws = (
                GREP_FOLLOW_UP_PREFIX
                + res
                + GREP_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )

    except (KeyError, TypeError, ValueError) as e:
        print(
            "grep_follow_up: crashed",
            {"type": type(e).__name__, "message": str(e)[:300]},
        )
        try:
            await ctx.toast(
                f"Grep workflow crashed: {type(e).__name__}: {str(e)[:120]}"
            )
        except (AttributeError, TypeError):
            pass

    if not chunk_ws:
        chunk_ws = (
            GREP_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + GREP_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        return FollowUpContribution(
            context_chunks=[chunk_ws],
            any_empty_tool=True,
        )

    return FollowUpContribution(
        context_chunks=[chunk_ws],
        any_empty_tool=False,
    )


__all__ = ["run_grep_follow_up"]
