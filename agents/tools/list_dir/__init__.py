"""
List_dir tool runner: list one or more directories concurrently via the
list_dir workflow.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from pydantic import JsonValue, TypeAdapter, ValidationError

from agents.chat.agent_workflow import (
    LIST_DIR_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.list_dir.follow_ups import (
    LIST_DIR_FOLLOW_UP_PREFIX,
    LIST_DIR_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import (
    FOLLOW_UP_EXTRA_LIST_DIR_FOLLOW_UP,
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)

EXECUTION_TIMEOUT_S: float = 30.0


def _empty_list_dir_contribution(
    hint: LanguageHintGetter,
) -> FollowUpContribution:
    language = (hint() or "English").strip() or "English"

    chunk = (
        LIST_DIR_FOLLOW_UP_PREFIX
        + TOOL_EMPTY_RESULT_LINE
        + LIST_DIR_FOLLOW_UP_SUFFIX.format(
            language=language,
            session_language=language,
        )
    )

    return FollowUpContribution(
        context_chunks=[chunk],
        any_empty_tool=True,
        extra={FOLLOW_UP_EXTRA_LIST_DIR_FOLLOW_UP: True},
    )


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


def _extract_list_dir_result(output: object) -> tuple[str, str]:
    if not isinstance(output, Mapping):
        return "", ""

    raw_data = output.get("data")
    raw_error = output.get("error")

    data = str(raw_data).strip() if raw_data is not None else ""
    error = ""

    if isinstance(raw_error, Mapping):
        if "error" in raw_error:
            raw_error = raw_error["error"]
        elif "message" in raw_error:
            raw_error = raw_error["message"]

    if raw_error is not None:
        error = str(raw_error).strip()

    return data, error


async def _run_one_list_dir(
    action: object,
) -> tuple[str, str | None]:
    """Run one normalized list_dir action."""

    payload: JsonValue = TypeAdapter(JsonValue).validate_python(
        action.model_dump(mode="json")  # type: ignore[union-attr]
    )

    out, errs = await run_workflow_with_errors(
        LIST_DIR_WORKFLOW_PATH,
        initial_inputs={
            "inject_payload": {
                "data": payload,
            }
        },
        format="dict",
        execution_timeout_s=EXECUTION_TIMEOUT_S,
    )

    workflow_error = _format_workflow_error(errs) if errs else None

    list_dir_output: object = {}

    if isinstance(out, Mapping):
        list_dir_output = out.get("list_dir") or {}

    list_dir_data, list_dir_error = _extract_list_dir_result(
        list_dir_output
    )

    # Preserve the original behavior: an explicit workflow error takes
    # precedence over normal directory-listing data.
    result = list_dir_error or list_dir_data

    if result:
        return result, None

    return "", workflow_error or list_dir_error


async def run_list_dir_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Keep this import local to avoid the action-block/follow-up import cycle.
    from agents.tools.list_dir.action_block import ListDirActionBlock

    try:
        ctx.set_inline_status("Inspecting folders…")
    except (AttributeError, TypeError):
        pass

    try:
        raw_actions = po.actions.get_tool_actions("list_dir")

        if not raw_actions:
            raise ValueError(
                "List-dir follow-up was requested, but no "
                "list_dir action was found"
            )

        # Validate every action before starting any workflow.
        actions = []

        for raw_action in raw_actions:
            try:
                actions.append(
                    ListDirActionBlock.model_validate(raw_action)
                )
            except ValidationError as exc:
                try:
                    if ctx.is_current_run(ctx.token):
                        await ctx.toast(
                            "Invalid list_dir action: "
                            f"{str(exc)[:120]}"
                        )
                except (AttributeError, TypeError):
                    pass

                raise

        # gather preserves action order while executing workflows concurrently.
        results = await asyncio.gather(
            *(_run_one_list_dir(action) for action in actions),
            return_exceptions=True,
        )

        language = (language_hint() or "English").strip() or "English"
        context_chunks: list[str] = []
        had_empty_result = False

        for result in results:
            if isinstance(result, BaseException):
                had_empty_result = True

                if isinstance(result, TimeoutError):
                    message = "List dir operation timed out"
                else:
                    message = (
                        "List dir workflow crashed: "
                        f"{type(result).__name__}: "
                        f"{str(result)[:120]}"
                    )

                try:
                    if ctx.is_current_run(ctx.token):
                        await ctx.toast(message)
                except (AttributeError, TypeError):
                    pass

                continue

            result_text, error_text = result

            if error_text and not result_text:
                had_empty_result = True

                try:
                    if ctx.is_current_run(ctx.token):
                        await ctx.toast(
                            f"List dir error: {error_text[:160]}"
                        )
                except (AttributeError, TypeError):
                    pass

                continue

            if not result_text:
                had_empty_result = True
                continue

            context_chunks.append(
                LIST_DIR_FOLLOW_UP_PREFIX
                + result_text
                + LIST_DIR_FOLLOW_UP_SUFFIX.format(
                    language=language,
                    session_language=language,
                )
            )

        if not context_chunks:
            return _empty_list_dir_contribution(language_hint)

        return FollowUpContribution(
            context_chunks=context_chunks,
            any_empty_tool=had_empty_result,
            extra={FOLLOW_UP_EXTRA_LIST_DIR_FOLLOW_UP: True},
        )

    except ValidationError:
        raise

    except (AttributeError, TypeError, KeyError, ValueError, IndexError) as exc:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast(
                    "List dir workflow crashed: "
                    f"{type(exc).__name__}: {str(exc)[:120]}"
                )
        except (AttributeError, TypeError):
            pass

        raise


__all__ = ["run_list_dir_follow_up"]
