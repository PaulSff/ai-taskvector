"""
make_dir follow-up: create a directory via the make_dir workflow.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue, TypeAdapter, ValidationError

from agents.chat.agent_workflow import (
    MAKE_DIR_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.make_dir.follow_ups import (
    MAKE_DIR_FOLLOW_UP_PREFIX,
    MAKE_DIR_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import (
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)

EXECUTION_TIMEOUT_S: float = 30.0


def _empty_make_dir_contribution(
    hint: LanguageHintGetter,
) -> FollowUpContribution:
    language = hint()

    chunk = (
        MAKE_DIR_FOLLOW_UP_PREFIX
        + TOOL_EMPTY_RESULT_LINE
        + MAKE_DIR_FOLLOW_UP_SUFFIX.format(
            language=language,
            session_language=language,
        )
    )

    return FollowUpContribution(
        context_chunks=[chunk],
        any_empty_tool=True,
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


def _extract_make_dir_result(output: object) -> tuple[str, str]:
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


async def run_make_dir_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Keep this import local to avoid the action-block/follow-up import cycle.
    from agents.tools.make_dir.action_block import MakeDirActionBlock

    try:
        ctx.set_inline_status("Creating new folder…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint

    try:
        make_dir_actions = po.actions.get_tool_actions("make_dir")

        if not make_dir_actions:
            raise ValueError(
                "Make-dir follow-up was requested, but no "
                "make_dir action was found"
            )

        if len(make_dir_actions) != 1:
            raise ValueError(
                "Make-dir follow-up expected exactly one make_dir action, "
                f"got {len(make_dir_actions)}"
            )

        raw_action = make_dir_actions[0]

        # Validate and normalize parser output using the authoritative schema.
        try:
            action = MakeDirActionBlock.model_validate(raw_action)
        except ValidationError as exc:
            try:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(
                        "Invalid make_dir action: "
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
                "template": payload,
            }
        }

        out, errs = await run_workflow_with_errors(
            MAKE_DIR_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs:
            error_text = _format_workflow_error(errs)

            try:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(f"Make dir error: {error_text}")
            except (AttributeError, TypeError):
                pass

        make_dir_output: object = {}

        if isinstance(out, Mapping):
            make_dir_output = out.get("make_dir") or {}

        make_dir_data, make_dir_error = _extract_make_dir_result(
            make_dir_output
        )

        # Prefer an explicit error returned by the workflow.
        result = make_dir_error or make_dir_data

        if not result:
            return _empty_make_dir_contribution(hint)

        language = hint()

        chunk = (
            MAKE_DIR_FOLLOW_UP_PREFIX
            + result
            + MAKE_DIR_FOLLOW_UP_SUFFIX.format(
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
                await ctx.toast("Make dir operation timed out")
        except (AttributeError, TypeError):
            pass

        return _empty_make_dir_contribution(hint)

    except ValidationError:
        raise

    except (AttributeError, TypeError, KeyError, ValueError, IndexError) as exc:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast(
                    "Make dir workflow crashed: "
                    f"{type(exc).__name__}: {str(exc)[:120]}"
                )
        except (AttributeError, TypeError):
            pass

        raise


__all__ = ["run_make_dir_follow_up"]
