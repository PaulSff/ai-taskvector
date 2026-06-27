"""get_chats follow-up: fetch chat list via TelegramClient workflow."""

from __future__ import annotations

import json
from typing import Any, Callable

from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.get_chats.follow_ups import (
    GET_CHATS_FOLLOW_UP_PREFIX,
    GET_CHATS_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import FollowUpContribution
from gui.chat.agent_workflow import (
    GET_CHATS_WORKFLOW_PATH,
    run_workflow_with_errors,
)

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


async def run_get_chats_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    action = po.get("get_unread") or po.get("get_chats")
    if not action:
        return FollowUpContribution(context_chunks=[], any_empty_tool=False)

    try:
        ctx.set_inline_status("Fetching chats…")
    except Exception:
        pass

    lang = language_hint()

    try:
        """
        One workflow run per element; each element is:
        { "action": "get_unread", "messenger": "telegram" }
        """
        actions = action if isinstance(action, list) else [action]
        context_chunks: list[str] = []
        any_empty = True

        for a in actions:
            out, errs = await run_workflow_with_errors(
                GET_CHATS_WORKFLOW_PATH,
                initial_inputs={"inject_get_unread": {"data": a}},
                format="dict",
                execution_timeout_s=EXECUTION_TIMEOUT_S,
            )
            if errs and ctx.is_current_run(ctx.token):
                await ctx.toast(f"Get chats error: {errs[0][1][:120]}")

            res = _format_telegram_result(out.get("tg_get_unread") or {})
            if res.strip():
                context_chunks.append(
                    GET_CHATS_FOLLOW_UP_PREFIX
                    + res
                    + GET_CHATS_FOLLOW_UP_SUFFIX.format(
                        language=lang,
                        session_language=lang,
                    )
                )
                any_empty = False
            else:
                context_chunks.append(
                    GET_CHATS_FOLLOW_UP_PREFIX
                    + TOOL_EMPTY_RESULT_LINE
                    + GET_CHATS_FOLLOW_UP_SUFFIX.format(
                        language=lang,
                        session_language=lang,
                    )
                )

        return FollowUpContribution(
            context_chunks=context_chunks, any_empty_tool=any_empty
        )

    except Exception:
        chunk = (
            GET_CHATS_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + GET_CHATS_FOLLOW_UP_SUFFIX.format(
                language=lang,
                session_language=lang,
            )
        )
        return FollowUpContribution(context_chunks=[chunk], any_empty_tool=True)


__all__ = ["run_get_chats_follow_up"]
