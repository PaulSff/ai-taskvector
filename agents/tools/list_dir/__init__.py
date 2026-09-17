"""
Browse follow-up: list a directory via the list_dir workflow.
"""

from __future__ import annotations

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
    language = hint()

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

    data = ""
    error = ""

    if raw_data is not None:
        data = str(raw_data).strip()

    if isinstance(raw_error, Mapping):
        raw_error = raw_error.get("error") or raw_error.get("message")

    if raw_error is not None:
        error = str(raw_error).strip()

    return data, error


async def run_list_dir_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Keep this import local to avoid the action-block/follow-up import cycle.
    from agents.tools.list_dir.action_block import ListDirActionBlock

    try:
        ctx.set_inline_status("Inspecting the folder…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint

    try:
        list_dir_actions = po.actions.get_tool_actions("list_dir")

        if not list_dir_actions:
            raise ValueError(
                "List-dir follow-up was requested, but no "
                "list_dir action was found"
            )

        if len(list_dir_actions) != 1:
            raise ValueError(
                "List-dir follow-up expected exactly one list_dir action, "
                f"got {len(list_dir_actions)}"
            )

        raw_action = list_dir_actions[0]

        # Validate and normalize parser output using the authoritative schema.
        try:
            action = ListDirActionBlock.model_validate(raw_action)
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

        # Pass the complete normalized action to the workflow.
        payload: JsonValue = TypeAdapter(JsonValue).validate_python(
            action.model_dump(mode="json")
        )

        initial_inputs = {
            "inject_payload": {
                "data": payload,
            }
        }

        out, errs = await run_workflow_with_errors(
            LIST_DIR_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs:
            error_text = _format_workflow_error(errs)

            try:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(f"List dir error: {error_text}")
            except (AttributeError, TypeError):
                pass

        list_dir_output: object = {}

        if isinstance(out, Mapping):
            list_dir_output = out.get("list_dir") or {}

        list_dir_data, list_dir_error = _extract_list_dir_result(
            list_dir_output
        )

        # Prefer an explicit error returned by the workflow.
        result = list_dir_error or list_dir_data

        if not result:
            return _empty_list_dir_contribution(hint)

        language = hint()

        chunk = (
            LIST_DIR_FOLLOW_UP_PREFIX
            + result
            + LIST_DIR_FOLLOW_UP_SUFFIX.format(
                language=language,
                session_language=language,
            )
        )

        return FollowUpContribution(
            context_chunks=[chunk],
            any_empty_tool=False,
            extra={FOLLOW_UP_EXTRA_LIST_DIR_FOLLOW_UP: True},
        )

    except TimeoutError:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast("List dir operation timed out")
        except (AttributeError, TypeError):
            pass

        return _empty_list_dir_contribution(hint)

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
