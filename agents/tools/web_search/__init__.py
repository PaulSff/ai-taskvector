from __future__ import annotations

import asyncio
from collections.abc import Mapping

from pydantic import ValidationError

from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.types import FollowUpContribution, LanguageHintGetter, ParserOutput
from core.schemas.primitives import WorkflowInputs

EXECUTION_TIMEOUT_S: float = 30.0


def _empty_web_search_contribution(
    hint: LanguageHintGetter,
) -> FollowUpContribution:
    from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
    from agents.tools.web_search.follow_ups import (
        WEB_SEARCH_FOLLOW_UP_PREFIX,
        WEB_SEARCH_FOLLOW_UP_SUFFIX,
    )

    language = (hint() or "English").strip() or "English"

    return FollowUpContribution(
        context_chunks=[
            WEB_SEARCH_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + WEB_SEARCH_FOLLOW_UP_SUFFIX.format(
                language=language,
                session_language=language,
            )
        ],
        any_empty_tool=True,
    )


def _extract_web_search_result(out: object) -> str:
    if not isinstance(out, Mapping):
        return ""

    web_search_result = out.get("web_search")
    if not isinstance(web_search_result, Mapping):
        return ""

    raw_result = web_search_result.get("out")
    if isinstance(raw_result, str):
        return raw_result.strip()

    if raw_result is not None:
        return str(raw_result).strip()

    return ""


async def _run_one_web_search(
    query: str,
    max_results: int,
) -> tuple[str, str]:
    from agents.chat.agent_workflow import (
        WEB_SEARCH_WORKFLOW_PATH,
        run_workflow_with_errors,
    )

    initial_inputs: WorkflowInputs = {
        "inject_query": {
            "template": query,
        }
    }

    unit_param_overrides: WorkflowInputs = {
        "web_search": {
            "safesearch": "off",
            "max_results": max_results,
        }
    }

    out, errs = await run_workflow_with_errors(
        WEB_SEARCH_WORKFLOW_PATH,
        initial_inputs=initial_inputs,
        unit_param_overrides=unit_param_overrides,
        format="dict",
        execution_timeout_s=EXECUTION_TIMEOUT_S,
    )

    return _extract_web_search_result(out), (
        errs[0][1] if errs else ""
    )


async def run_web_search_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    from agents.tools.web_search.action_block import WebSearchActionBlock
    from agents.tools.web_search.follow_ups import (
        WEB_SEARCH_FOLLOW_UP_PREFIX,
        WEB_SEARCH_FOLLOW_UP_SUFFIX,
    )

    try:
        ctx.set_inline_status("Searching the web…")
    except (AttributeError, TypeError):
        pass

    try:
        web_search_actions = po.actions.get_tool_actions("web_search")
        if not web_search_actions:
            raise ValueError(
                "Web search follow-up was requested, but no "
                "web_search action was found"
            )

        validated_actions: list[WebSearchActionBlock] = []
        for raw_action in web_search_actions:
            validated_actions.append(WebSearchActionBlock.model_validate(raw_action))

        queries: list[str] = []
        tasks: list[asyncio.Task[tuple[str, str]]] = []

        for action in validated_actions:
            query = action.query.strip()
            if not query:
                continue

            max_results = max(1, min(int(action.max_results), 20))
            queries.append(query)
            tasks.append(asyncio.create_task(_run_one_web_search(query, max_results)))

        if not tasks:
            return _empty_web_search_contribution(language_hint)

        results = await asyncio.gather(*tasks)

        language = (language_hint() or "English").strip() or "English"
        context_chunks: list[str] = []
        had_empty_result = False

        for query, (result, error) in zip(queries, results, strict=True):
            if error:
                had_empty_result = True
                try:
                    await ctx.toast(
                        f"Web search error for {query[:60]!r}: {error[:120]}"
                    )
                except (AttributeError, TypeError):
                    pass

            if not result:
                had_empty_result = True
                continue

            context_chunks.append(
                WEB_SEARCH_FOLLOW_UP_PREFIX
                + f"--- Query: {query} ---\n"
                + result
                + WEB_SEARCH_FOLLOW_UP_SUFFIX.format(
                    language=language,
                    session_language=language,
                )
            )

        if not context_chunks:
            return _empty_web_search_contribution(language_hint)

        return FollowUpContribution(
            context_chunks=context_chunks,
            any_empty_tool=had_empty_result,
        )

    except TimeoutError:
        try:
            await ctx.toast("Web search timed out")
        except (AttributeError, TypeError):
            pass

        return _empty_web_search_contribution(language_hint)

    except ValidationError as exc:
        try:
            await ctx.toast(
                "Invalid web search action: "
                f"{str(exc)[:120]}"
            )
        except (AttributeError, TypeError):
            pass
        raise

    except (KeyError, TypeError, ValueError, IndexError) as exc:
        try:
            await ctx.toast(
                "Web search workflow crashed: "
                f"{type(exc).__name__}: {str(exc)[:120]}"
            )
        except (AttributeError, TypeError):
            pass
        raise


__all__ = ["run_web_search_follow_up"]
