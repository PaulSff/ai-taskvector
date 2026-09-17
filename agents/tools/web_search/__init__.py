from __future__ import annotations

from collections.abc import Mapping

from pydantic import ValidationError

from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.tools.types import FollowUpContribution, LanguageHintGetter, ParserOutput

EXECUTION_TIMEOUT_S: float = 30.0


def _empty_web_search_contribution(
    hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Lazy imports prevent web_search.__init__ from importing this module
    # while it is still being initialized.
    from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
    from agents.tools.types import FollowUpContribution
    from agents.tools.web_search.follow_ups import (
        WEB_SEARCH_FOLLOW_UP_PREFIX,
        WEB_SEARCH_FOLLOW_UP_SUFFIX,
    )

    return FollowUpContribution(
        context_chunks=[
            WEB_SEARCH_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + WEB_SEARCH_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        ],
        any_empty_tool=True,
    )


def _extract_web_search_result(out: object) -> str:
    """
    Extract the serialized web-search result from the workflow output.

    Expected workflow shape:

        {
            "web_search": {
                "out": "..."
            }
        }
    """
    if not isinstance(out, Mapping):
        return ""

    web_search_result = out.get("web_search")

    if not isinstance(web_search_result, Mapping):
        return ""

    raw_result = web_search_result.get("out")

    if isinstance(raw_result, str):
        return raw_result.strip()

    # Keep this defensive in case the web-search workflow returns
    # structured or list data in the future.
    if raw_result is not None:
        return str(raw_result).strip()

    return ""


async def run_web_search_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # All application imports are intentionally local. This avoids the cycle:

    # web_search.__init__
    #   -> action_block
    #   -> follow_ups
    #   -> agent_workflow
    #   -> settings / web_search package

    from agents.chat.agent_workflow import (
        WEB_SEARCH_WORKFLOW_PATH,
        run_workflow_with_errors,
    )
    from agents.tools.types import FollowUpContribution
    from agents.tools.web_search.action_block import (
        WebSearchActionBlock,
    )
    from agents.tools.web_search.follow_ups import (
        WEB_SEARCH_FOLLOW_UP_PREFIX,
        WEB_SEARCH_FOLLOW_UP_SUFFIX,
    )
    from core.schemas.primitives import WorkflowInputs

    try:
        ctx.set_inline_status("Searching the web…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint

    try:
        web_search_actions = po.actions.get_tool_actions(
            "web_search"
        )

        if not web_search_actions:
            raise ValueError(
                "Web search follow-up was requested, but no "
                "web_search action was found"
            )

        raw_action = web_search_actions[0]

        # Validate and normalize the parser output using the
        # authoritative ActionBlock schema.
        try:
            action = WebSearchActionBlock.model_validate(raw_action)
        except ValidationError as exc:
            raise ValueError(
                "Invalid web_search action block: "
                f"{raw_action!r}; errors={exc.errors()!r}"
            ) from exc

        query = action.query.strip()
        max_results = max(1, min(int(action.max_results), 20))

        print(
            "[run_web_search_follow_up] "
            "validated action "
            f"query={query!r} "
            f"max_results={max_results}",
            flush=True,
        )

        initial_inputs: WorkflowInputs = {
            "inject_query": {
                "template": query,
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
            "calling run_workflow_with_errors "
            f"query={query[:120]!r} "
            f"max_results={max_results}",
            flush=True,
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
            "run_workflow_with_errors returned "
            f"errs_len={len(errs)} "
            f"out_type={type(out).__name__} "
            f"out_keys={list(out.keys()) if isinstance(out, Mapping) else None}",
            flush=True,
        )

        if errs:
            print(
                "[run_web_search_follow_up] "
                f"workflow_errors={errs!r}",
                flush=True,
            )

            try:
                await ctx.toast(
                    f"Web search error: {errs[0][1][:120]}"
                )
            except (AttributeError, TypeError, IndexError):
                pass

        result = _extract_web_search_result(out)

        print(
            "[run_web_search_follow_up] "
            f"extracted_result_len={len(result)} "
            f"result_preview={result[:500]!r}",
            flush=True,
        )

        if not result:
            print(
                "[run_web_search_follow_up] "
                "no extractable web-search result",
                flush=True,
            )
            return _empty_web_search_contribution(hint)

        chunk = (
            WEB_SEARCH_FOLLOW_UP_PREFIX
            + result
            + WEB_SEARCH_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )

        return FollowUpContribution(
            context_chunks=[chunk],
            any_empty_tool=False,
        )

    except TimeoutError:
        try:
            await ctx.toast("Web search timed out")
        except (AttributeError, TypeError):
            pass

        return _empty_web_search_contribution(hint)

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
