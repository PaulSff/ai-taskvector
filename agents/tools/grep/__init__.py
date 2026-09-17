from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue, TypeAdapter, ValidationError

from agents.chat.agent_workflow import (
    GREP_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.grep.follow_ups import (
    GREP_FOLLOW_UP_PREFIX,
    GREP_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import (
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)

EXECUTION_TIMEOUT_S: float = 60.0


def _empty_grep_contribution(
    hint: LanguageHintGetter,
) -> FollowUpContribution:
    language = hint()

    chunk = (
        GREP_FOLLOW_UP_PREFIX
        + TOOL_EMPTY_RESULT_LINE
        + GREP_FOLLOW_UP_SUFFIX.format(
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


def _format_grep_result(grep_output: object) -> str:
    if not isinstance(grep_output, Mapping):
        return ""

    output = grep_output.get("out")
    error = grep_output.get("error")

    result = ""

    if output is not None:
        result = str(output).strip()

    if isinstance(error, Mapping):
        error = error.get("error") or error.get("message")

    if error is not None and str(error).strip():
        error_text = str(error).strip()
        result = (
            f"{result}\nError: {error_text}".strip()
            if result
            else f"Error: {error_text}"
        )

    return result


async def run_grep_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Keep this import local to avoid the action-block/follow-up import cycle.
    from agents.tools.grep.action_block import GrepActionBlock

    try:
        setter = getattr(ctx, "set_inline_status", None)
        if callable(setter):
            setter("Using grep…")
    except (AttributeError, TypeError, RuntimeError):
        pass

    hint = language_hint

    try:
        grep_actions = po.actions.get_tool_actions("grep")

        if not grep_actions:
            raise ValueError(
                "Grep follow-up was requested, but no grep action was found"
            )

        if len(grep_actions) != 1:
            raise ValueError(
                "Grep follow-up expected exactly one grep action, "
                f"got {len(grep_actions)}"
            )

        raw_action = grep_actions[0]

        # Validate and normalize parser output using the authoritative schema.
        try:
            action = GrepActionBlock.model_validate(raw_action)
        except ValidationError as exc:
            try:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(
                        "Invalid grep action: "
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
            GREP_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            unit_param_overrides=None,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs:
            error_text = _format_workflow_error(errs)

            try:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(f"Grep error: {error_text}")
            except (AttributeError, TypeError):
                pass

        grep_output: object = {}

        if isinstance(out, Mapping):
            grep_output = out.get("grep") or {}

        result = _format_grep_result(grep_output)

        if not result.strip():
            return _empty_grep_contribution(hint)

        language = hint()

        chunk = (
            GREP_FOLLOW_UP_PREFIX
            + result
            + GREP_FOLLOW_UP_SUFFIX.format(
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
                await ctx.toast("Grep operation timed out")
        except (AttributeError, TypeError):
            pass

        return _empty_grep_contribution(hint)

    except ValidationError:
        raise

    except (AttributeError, TypeError, KeyError, ValueError, IndexError) as exc:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast(
                    "Grep workflow crashed: "
                    f"{type(exc).__name__}: {str(exc)[:120]}"
                )
        except (AttributeError, TypeError):
            pass

        raise


__all__ = ["run_grep_follow_up"]
