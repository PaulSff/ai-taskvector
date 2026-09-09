from __future__ import annotations

from collections.abc import Mapping

from agents.chat.agent_workflow import (
    WEB_SEARCH_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.types import FollowUpContribution, LanguageHintGetter, ParserOutput
from agents.tools.web_search.follow_ups import (
    WEB_SEARCH_FOLLOW_UP_PREFIX,
    WEB_SEARCH_FOLLOW_UP_SUFFIX,
)
from core.schemas.primitives import Data, WorkflowInputs
from units.web import register_web_units

EXECUTION_TIMEOUT_S: float = 30.0


async def run_web_search_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    try:
        ctx.set_inline_status("Searching web…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint
    chunk_ws: str | None = None

    try:
        register_web_units()

        web_search_actions = po.actions.get_tool_actions("web_search")
        web_search_data: Data = (
            web_search_actions[0] if web_search_actions else {}
        )

        q = web_search_data.get("web_search", "")

        if isinstance(q, (list, tuple)):
            q = " ".join(map(str, q))

        q = "" if q is None else str(q).strip()

        raw_max_results = web_search_data.get(
            "web_search_max_results",
            10,
        )

        if isinstance(raw_max_results, bool):
            max_results = 10
        elif isinstance(raw_max_results, (str, int, float)):
            try:
                max_results = int(raw_max_results)
            except ValueError:
                max_results = 10
        else:
            max_results = 10

        max_results = max(1, min(max_results, 20))

        initial_inputs: WorkflowInputs = {
            "inject_query": {
                "data": q,
            }
        }

        unit_param_overrides = {
            "web_search": {
                "safesearch": "off",
                "max_results": max_results,
            }
        }

        print(
            "[run_web_search_follow_up] "
            f"calling run_workflow_with_errors "
            f"q={q[:80]!r} max_results={max_results}"
        )

        out, errs = await run_workflow_with_errors(
            WEB_SEARCH_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        print(
            "[run_web_search_follow_up] "
            f"run_workflow_with_errors returned "
            f"errs_len={len(errs)} "
            f"out_keys={list((out or {}).keys())}"
        )

        if errs:
            try:
                await ctx.toast(
                    f"Web search error: {errs[0][1][:120]}"
                )
            except (AttributeError, TypeError, IndexError):
                pass

        res = ""

        if isinstance(out, Mapping):
            web_search_result = out.get("web_search")

            if isinstance(web_search_result, Mapping):
                raw_res = web_search_result.get("out")

                if isinstance(raw_res, str):
                    res = raw_res


        if res.strip():
            chunk_ws = (
                WEB_SEARCH_FOLLOW_UP_PREFIX
                + res
                + WEB_SEARCH_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )

    except (KeyError, TypeError, ValueError, IndexError) as e:
        try:
            await ctx.toast(
                "Web search workflow crashed: "
                f"{type(e).__name__}: {str(e)[:120]}"
            )
        except (AttributeError, TypeError):
            pass

    if not chunk_ws:
        chunk_ws = (
            WEB_SEARCH_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + WEB_SEARCH_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )

        return FollowUpContribution(
            context_chunks=[chunk_ws],
            any_empty_tool=True,
        )

    return FollowUpContribution(
        context_chunks=[chunk_ws],
        any_empty_tool=False,
    )


__all__ = ["run_web_search_follow_up"]
