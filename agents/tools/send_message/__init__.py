"""
send_message follow-up: send a chat message via TelegramClient workflow.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from pydantic import JsonValue, TypeAdapter, ValidationError

from agents.chat.agent_workflow import (
    SEND_MESSAGE_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.send_message.follow_ups import (
    SEND_MESSAGE_FOLLOW_UP_PREFIX,
    SEND_MESSAGE_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import (
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)
from core.schemas.primitives import WorkflowInputs

EXECUTION_TIMEOUT_S: float = 30.0


def _empty_send_message_chunk(hint: LanguageHintGetter) -> str:
    language = hint()

    return (
        SEND_MESSAGE_FOLLOW_UP_PREFIX
        + TOOL_EMPTY_RESULT_LINE
        + SEND_MESSAGE_FOLLOW_UP_SUFFIX.format(
            language=language,
            session_language=language,
        )
    )


def _format_workflow_error(errs: object) -> str:
    if not errs:
        return "unknown workflow error"

    if isinstance(errs, str):
        return errs[:120]

    try:
        first_error = errs[0]  # type: ignore[index]
    except (IndexError, TypeError, KeyError):
        return str(errs)[:120]

    if isinstance(first_error, (tuple, list)) and len(first_error) > 1:
        return str(first_error[1])[:120]

    return str(first_error)[:120]


def _format_telegram_result(output: object) -> str:
    if not isinstance(output, Mapping):
        return ""

    raw_error = output.get("error")

    if isinstance(raw_error, Mapping):
        message = raw_error.get("error") or raw_error.get("message")
        if message:
            return f"Error: {message}"

    if isinstance(raw_error, str) and raw_error.strip():
        return f"Error: {raw_error.strip()}"

    status = output.get("status")

    if isinstance(status, Mapping):
        current_status = status.get("status")
        if current_status:
            return f"Status: {current_status}"

    update = output.get("update")

    if update is None:
        return ""

    payload = update

    if isinstance(update, Mapping) and update.get("type") == "update":
        payload = update.get("update", update)

    try:
        body = json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    except (TypeError, ValueError):
        body = str(payload)

    if len(body) > 8000:
        body = body[:8000] + "\n... (truncated)"

    return body


def _get_send_message_actions(po: ParserOutput) -> list[object]:
    raw_actions = po.actions.get_tool_actions("send_message")

    if not raw_actions:
        raise ValueError(
            "Send-message follow-up was requested, but no "
            "send_message action was found"
        )

    return list(raw_actions)


def _normalize_send_message_action(raw_action: object) -> JsonValue:
    # Keep this import local to avoid the action-block/follow-up import cycle.
    from agents.tools.send_message.action_block import (
        SendMessageActionBlock,
    )

    try:
        action = SendMessageActionBlock.model_validate(raw_action)
    except ValidationError as exc:
        raise ValueError(
            f"Invalid send_message action: {str(exc)[:120]}"
        ) from exc

    return TypeAdapter(JsonValue).validate_python(
        action.model_dump(mode="json")
    )


async def run_send_message_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    try:
        ctx.set_inline_status("Sending message…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint
    language = hint()

    try:
        raw_actions = _get_send_message_actions(po)

        context_chunks: list[str] = []
        any_empty = False

        for raw_action in raw_actions:
            payload = _normalize_send_message_action(raw_action)

            # Each message is intentionally executed in its own workflow run.
            initial_inputs: WorkflowInputs = {
                "inject_send_message": {
                    "template": payload,
                }
            }

            out, errs = await run_workflow_with_errors(
                SEND_MESSAGE_WORKFLOW_PATH,
                initial_inputs=initial_inputs,
                format="dict",
                execution_timeout_s=EXECUTION_TIMEOUT_S,
            )

            if errs:
                error_text = _format_workflow_error(errs)

                try:
                    if ctx.is_current_run(ctx.token):
                        await ctx.toast(
                            f"Send message error: {error_text}"
                        )
                except (AttributeError, TypeError):
                    pass

            workflow_output: object = {}

            if isinstance(out, Mapping):
                workflow_output = out.get("tg_send_message") or {}

            result = _format_telegram_result(workflow_output)

            if not result:
                context_chunks.append(_empty_send_message_chunk(hint))
                any_empty = True
                continue

            context_chunks.append(
                SEND_MESSAGE_FOLLOW_UP_PREFIX
                + result
                + SEND_MESSAGE_FOLLOW_UP_SUFFIX.format(
                    language=language,
                    session_language=language,
                )
            )

        if not context_chunks:
            return FollowUpContribution(
                context_chunks=[_empty_send_message_chunk(hint)],
                any_empty_tool=True,
            )

        return FollowUpContribution(
            context_chunks=context_chunks,
            any_empty_tool=any_empty,
        )

    except TimeoutError:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast("Send message operation timed out")
        except (AttributeError, TypeError):
            pass

        return FollowUpContribution(
            context_chunks=[_empty_send_message_chunk(hint)],
            any_empty_tool=True,
        )

    except ValidationError:
        raise

    except (AttributeError, TypeError, KeyError, ValueError, IndexError):
        raise


__all__ = ["run_send_message_follow_up"]
