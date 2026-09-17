"""get_chats follow-up: fetch unread chats via TelegramClient workflow."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue, TypeAdapter, ValidationError

from agents.chat.agent_workflow import (
    GET_CHATS_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.get_chats.follow_ups import (
    GET_CHATS_FOLLOW_UP_PREFIX,
    GET_CHATS_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import (
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)

EXECUTION_TIMEOUT_S: float = 30.0


def _empty_get_chats_contribution(
    hint: LanguageHintGetter,
) -> FollowUpContribution:
    language = hint()

    chunk = (
        GET_CHATS_FOLLOW_UP_PREFIX
        + TOOL_EMPTY_RESULT_LINE
        + GET_CHATS_FOLLOW_UP_SUFFIX.format(
            language=language,
            session_language=language,
        )
    )

    return FollowUpContribution(
        context_chunks=[chunk],
        any_empty_tool=True,
    )


def _format_telegram_result(tg_out: object) -> str:
    if not isinstance(tg_out, Mapping):
        return ""

    error = tg_out.get("error")

    if isinstance(error, Mapping):
        message = error.get("error") or error.get("message")
        if message:
            return f"Error: {message}"

    if isinstance(error, str) and error.strip():
        return f"Error: {error.strip()}"

    status = tg_out.get("status")

    if isinstance(status, Mapping):
        status_value = status.get("status")
        if status_value:
            return f"Status: {status_value}"

    update = tg_out.get("update")

    if update is None:
        return ""

    payload = update

    if isinstance(update, Mapping) and update.get("type") == "update":
        payload = update.get("update", update)

    try:
        import json

        body = json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        body = f"{payload!r}\n(Note: serialization failed: {exc})"

    if len(body) > 8000:
        body = body[:8000] + "\n... (truncated)"

    return body


def _format_workflow_error(errs: object) -> str:
    if not errs:
        return "unknown workflow error"

    try:
        first_error = errs[0]  # type: ignore[index]
    except (IndexError, TypeError):
        return str(errs)[:120]

    if isinstance(first_error, (tuple, list)) and len(first_error) > 1:
        return str(first_error[1])[:120]

    return str(first_error)[:120]


async def run_get_chats_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Keep this import local to avoid the action-block/follow-up import cycle.
    from agents.tools.get_chats.action_block import GetUnreadActionBlock

    try:
        ctx.set_inline_status("Fetching chats…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint

    try:
        get_unread_actions = po.actions.get_tool_actions("get_unread")

        if not get_unread_actions:
            raise ValueError(
                "Get-chats follow-up was requested, but no "
                "get_unread action was found"
            )

        if len(get_unread_actions) != 1:
            raise ValueError(
                "Get-chats follow-up expected exactly one get_unread action, "
                f"got {len(get_unread_actions)}"
            )

        raw_action = get_unread_actions[0]

        # Validate and normalize parser output using the authoritative schema.
        try:
            action = GetUnreadActionBlock.model_validate(raw_action)
        except ValidationError as exc:
            try:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(
                        "Invalid get_unread action: "
                        f"{str(exc)[:120]}"
                    )
            except (AttributeError, TypeError):
                pass

            raise

        # Convert the complete normalized action into workflow-compatible JSON.
        payload: JsonValue = TypeAdapter(JsonValue).validate_python(
            action.model_dump(mode="json")
        )

        initial_inputs = {
            "inject_get_unread": {
                "template": payload,
            }
        }

        out, errs = await run_workflow_with_errors(
            GET_CHATS_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs:
            error_text = _format_workflow_error(errs)

            try:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(f"Get chats error: {error_text}")
            except (AttributeError, TypeError):
                pass

        tg_output: object = {}

        if isinstance(out, Mapping):
            tg_output = out.get("tg_get_unread") or {}

        result = _format_telegram_result(tg_output)

        if not result.strip():
            return _empty_get_chats_contribution(hint)

        language = hint()

        chunk = (
            GET_CHATS_FOLLOW_UP_PREFIX
            + result
            + GET_CHATS_FOLLOW_UP_SUFFIX.format(
                language=language,
                session_language=language,
            )
        )

        return FollowUpContribution(
            context_chunks=[chunk],
            any_empty_tool=False,
        )

    except TimeoutError:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast("Get chats operation timed out")
        except (AttributeError, TypeError):
            pass

        return _empty_get_chats_contribution(hint)

    except ValidationError:
        raise

    except (AttributeError, TypeError, KeyError, ValueError, IndexError) as exc:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast(
                    "Get chats workflow crashed: "
                    f"{type(exc).__name__}: {str(exc)[:120]}"
                )
        except (AttributeError, TypeError):
            pass

        raise


__all__ = ["run_get_chats_follow_up"]
