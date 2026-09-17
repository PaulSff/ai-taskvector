"""GitHub follow-up: execute a GitHub API workflow."""

from __future__ import annotations

import json
from collections.abc import Mapping

from pydantic import JsonValue, TypeAdapter, ValidationError

from agents.chat.agent_workflow import (
    GITHUB_GET_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.github.follow_ups import (
    GITHUB_FOLLOW_UP_PREFIX,
    GITHUB_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import (
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)

EXECUTION_TIMEOUT_S: float = 30.0


def _empty_github_contribution(
    hint: LanguageHintGetter,
) -> FollowUpContribution:
    language = hint()

    chunk = (
        GITHUB_FOLLOW_UP_PREFIX
        + TOOL_EMPTY_RESULT_LINE
        + GITHUB_FOLLOW_UP_SUFFIX.format(
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


def _format_github_result(github_output: object) -> str:
    if not isinstance(github_output, Mapping):
        return ""

    error = github_output.get("error")

    if isinstance(error, Mapping):
        error_message = error.get("error") or error.get("message")
        if error_message:
            return f"Error: {error_message}"

    elif error is not None and str(error).strip():
        return f"Error: {str(error).strip()}"

    data = github_output.get("data")

    if data is None:
        return ""

    try:
        result = json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    except (TypeError, ValueError, OverflowError):
        result = str(data)

    if len(result) > 8000:
        result = result[:8000] + "\n... (truncated)"

    return result


async def run_github_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Keep this import local to avoid the action-block/follow-up import cycle.
    from agents.tools.github.action_block import GithubActionBlock

    try:
        ctx.set_inline_status("Querying GitHub…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint

    try:
        github_actions = po.actions.get_tool_actions("github")

        if not github_actions:
            raise ValueError(
                "GitHub follow-up was requested, but no github action was found"
            )

        if len(github_actions) != 1:
            raise ValueError(
                "GitHub follow-up expected exactly one github action, "
                f"got {len(github_actions)}"
            )

        raw_action = github_actions[0]

        # Validate and normalize parser output using the authoritative schema.
        try:
            action = GithubActionBlock.model_validate(raw_action)
        except ValidationError as exc:
            try:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(
                        "Invalid GitHub action: "
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
            "inject_action": {
                "template": payload,
            }
        }

        out, errs = await run_workflow_with_errors(
            GITHUB_GET_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs:
            error_text = _format_workflow_error(errs)

            try:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(f"GitHub error: {error_text}")
            except (AttributeError, TypeError):
                pass

        github_output: object = {}

        if isinstance(out, Mapping):
            github_output = out.get("github_get") or {}

        result = _format_github_result(github_output)

        if not result.strip():
            return _empty_github_contribution(hint)

        language = hint()

        chunk = (
            GITHUB_FOLLOW_UP_PREFIX
            + result
            + GITHUB_FOLLOW_UP_SUFFIX.format(
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
                await ctx.toast("GitHub operation timed out")
        except (AttributeError, TypeError):
            pass

        return _empty_github_contribution(hint)

    except ValidationError:
        raise

    except (AttributeError, TypeError, KeyError, ValueError, IndexError) as exc:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast(
                    "GitHub workflow crashed: "
                    f"{type(exc).__name__}: {str(exc)[:120]}"
                )
        except (AttributeError, TypeError):
            pass

        raise


__all__ = ["run_github_follow_up"]
