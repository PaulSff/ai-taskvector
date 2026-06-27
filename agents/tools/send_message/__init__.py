"""send_message follow-up: send a chat message via TelegramClient workflow."""

from __future__ import annotations

import json
from typing import Any, Callable

from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.send_message.follow_ups import (
    SEND_MESSAGE_FOLLOW_UP_PREFIX,
    SEND_MESSAGE_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import FollowUpContribution
from gui.chat.agent_workflow import (
    SEND_MESSAGE_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from units.messengers import register_messengers_units

EXECUTION_TIMEOUT_S: float = 30.0


def _format_telegram_result(tg_out: dict[str, Any]) -> str:
    err = tg_out.get("error")
    if isinstance(err, dict):
        msg = err.get("error") or err.get("message")
        if msg:
            return f"Error: {msg}"
    if isinstance(err, str) and err.strip():
        return f"Error: {err.strip()}"

    status = tg_out.get("status")
    if isinstance(status, dict):
        st = status.get("status")
        if st:
            return f"Status: {st}"

    update = tg_out.get("update")
    if update is not None:
        payload = update
        if isinstance(update, dict) and update.get("type") == "update":
            payload = update.get("update", update)
        try:
            body = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
        except Exception:
            body = str(payload)
        if len(body) > 8000:
            body = body[:8000] + "\n... (truncated)"
        return body
    return ""


async def run_send_message_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    action = po.get("send_message")
    if not action:
        return FollowUpContribution(context_chunks=[], any_empty_tool=False)

    try:
        ctx.set_inline_status("Sending message…")
    except Exception:
        pass

    hint = language_hint
    chunk: str | None = None
    try:
        register_messengers_units()
        out, errs = await run_workflow_with_errors(
            SEND_MESSAGE_WORKFLOW_PATH,
            initial_inputs={"inject_send_message": {"data": action}},
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )
        if errs and ctx.is_current_run(ctx.token):
            await ctx.toast(f"Send message error: {errs[0][1][:120]}")
        res = _format_telegram_result(out.get("tg_send_message") or {})
        if res.strip():
            chunk = (
                SEND_MESSAGE_FOLLOW_UP_PREFIX
                + res
                + SEND_MESSAGE_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
    except Exception:
        pass

    if not chunk:
        chunk = (
            SEND_MESSAGE_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + SEND_MESSAGE_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        return FollowUpContribution(context_chunks=[chunk], any_empty_tool=True)
    return FollowUpContribution(context_chunks=[chunk], any_empty_tool=False)


__all__ = ["run_send_message_follow_up"]
