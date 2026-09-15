"""Browse follow-up: fetch URL content via the browser workflow."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from pydantic import ValidationError

from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.types import (
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)

EXECUTION_TIMEOUT_S: float = 30.0


def _empty_browse_contribution(
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    from agents.tools.browse.follow_ups import (
        BROWSE_FOLLOW_UP_PREFIX,
        BROWSE_FOLLOW_UP_SUFFIX,
    )

    language = language_hint()

    return FollowUpContribution(
        context_chunks=[
            BROWSE_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + BROWSE_FOLLOW_UP_SUFFIX.format(
                language=language,
                session_language=language,
            )
        ],
        any_empty_tool=True,
    )


def _extract_browse_result(out: object) -> str:
    """Extract the serialized browser result from workflow output."""

    if not isinstance(out, Mapping):
        return ""

    beautifulsoup_result = out.get("beautifulsoup")

    if not isinstance(beautifulsoup_result, Mapping):
        return ""

    raw_result = beautifulsoup_result.get("out")

    if isinstance(raw_result, str):
        return raw_result.strip()

    if raw_result is not None:
        return str(raw_result).strip()

    return ""


async def _safe_toast(
    ctx: ExecutionFollowUpContext,
    message: str,
) -> None:
    try:
        if ctx.is_current_run(ctx.token):
            await ctx.toast(message)
    except (AttributeError, TypeError, IndexError):
        pass


def _safe_set_inline_status(
    ctx: ExecutionFollowUpContext,
    status: str,
) -> None:
    try:
        ctx.set_inline_status(status)
    except (AttributeError, TypeError):
        pass


async def run_browse_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    """
    Browse all requested URLs concurrently.

    Results are returned in the same order as the original browse actions.
    A failure for one URL does not prevent the remaining URLs from completing.
    """

    # Keep these imports local to avoid import cycles during tool registration.
    from agents.chat.agent_workflow import (
        BROWSER_WORKFLOW_PATH,
        run_workflow_with_errors,
    )
    from agents.tools.browse.action_block import BrowseActionBlock
    from agents.tools.browse.follow_ups import (
        BROWSE_FOLLOW_UP_PREFIX,
        BROWSE_FOLLOW_UP_SUFFIX,
    )

    _safe_set_inline_status(ctx, "Loading pages…")

    browse_actions = po.actions.get_tool_actions("browse")

    if not browse_actions:
        raise ValueError(
            "Browse follow-up was requested, but no browse action was found"
        )

    async def browse_one(
        raw_action: object,
    ) -> tuple[str, bool]:
        """
        Browse one URL.

        Returns:
            A tuple containing:
            - the extracted page content, or an empty string
            - whether the action failed or produced no content
        """
        try:
            try:
                action = BrowseActionBlock.model_validate(raw_action)
            except ValidationError as exc:
                raise ValueError(
                    "Invalid browse action block: "
                    f"{raw_action!r}; errors={exc.errors()!r}"
                ) from exc

            url = action.url.strip()

            if not url:
                raise ValueError("Browse action URL cannot be empty")

            out, errs = await run_workflow_with_errors(
                BROWSER_WORKFLOW_PATH,
                initial_inputs={
                    "inject_url": {
                        "data": url,
                    }
                },
                format="dict",
                execution_timeout_s=EXECUTION_TIMEOUT_S,
            )

            if errs:
                await _safe_toast(
                    ctx,
                    f"Browse error: {errs[0][1][:120]}",
                )

            result = _extract_browse_result(out)

            if not result:
                return "", True

            return result, False

        except TimeoutError:
            await _safe_toast(ctx, "Browse timed out")
            return "", True

        except (KeyError, TypeError, ValueError, IndexError) as exc:
            await _safe_toast(
                ctx,
                "Browse workflow crashed: "
                f"{type(exc).__name__}: {str(exc)[:120]}",
            )
            return "", True

    # gather() executes all browse operations concurrently while preserving
    # the original action order in the returned results.
    results = await asyncio.gather(
        *(browse_one(raw_action) for raw_action in browse_actions)
    )

    language = language_hint()
    context_chunks: list[str] = []

    for result, _was_empty in results:
        if not result:
            continue

        context_chunks.append(
            BROWSE_FOLLOW_UP_PREFIX
            + result
            + BROWSE_FOLLOW_UP_SUFFIX.format(
                language=language,
                session_language=language,
            )
        )

    if not context_chunks:
        return _empty_browse_contribution(language_hint)

    return FollowUpContribution(
        context_chunks=context_chunks,
        any_empty_tool=any(
            was_empty
            for _, was_empty in results
        ),
    )


__all__ = ["run_browse_follow_up"]
