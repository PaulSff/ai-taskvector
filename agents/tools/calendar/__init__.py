from __future__ import annotations

from typing import Any, Callable

from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.types import FollowUpContribution
from agents.tools.calendar.follow_ups import (
    CALENDAR_FOLLOW_UP_PREFIX,
    CALENDAR_FOLLOW_UP_SUFFIX,
)
from gui.chat.agent_workflow import (
    CALENDAR_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from units.time import register_time_units

EXECUTION_TIMEOUT_S: float = 30.0


async def run_calendar_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    try:
        ctx.set_inline_status("Using calendar…")
    except Exception:
        pass

    hint = language_hint
    chunk_ws: str | None = None

    try:
        register_time_units()

        action_obj = po["calendar"]  # required:
        # { "action": "create_calendar" | "get_all_calendars" | "check_availability" | "reserve" | "cancel", ... }

        initial_inputs = {"trigger_inject": {"template": action_obj}}

        out, errs = await run_workflow_with_errors(
            CALENDAR_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            unit_param_overrides=None,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs:
            try:
                await ctx.toast(f"Calendar error: {errs[0][1][:120]}")
            except Exception:
                pass

        calendar_out = (out or {}).get("calendar") or {}
        calendar_data = calendar_out.get("data")
        calendar_error_port = calendar_out.get("error") or ""

        res = ""
        if isinstance(calendar_data, dict):
            if calendar_data.get("ok") is True:
                res = str(calendar_data)
            else:
                # expected by unit contract: calendar_data["error"] contains details
                res = str(calendar_data.get("error") or calendar_error_port or "")
        else:
            res = str(calendar_data or "")

        if res.strip():
            chunk_ws = (
                CALENDAR_FOLLOW_UP_PREFIX
                + res
                + CALENDAR_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )

    except Exception as e:
        try:
            await ctx.toast(
                f"Calendar workflow crashed: {type(e).__name__}: {str(e)[:120]}"
            )
        except Exception:
            pass

    if not chunk_ws:
        chunk_ws = (
            CALENDAR_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + CALENDAR_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        return FollowUpContribution(context_chunks=[chunk_ws], any_empty_tool=True)

    return FollowUpContribution(context_chunks=[chunk_ws], any_empty_tool=False)


__all__ = ["run_calendar_follow_up"]
