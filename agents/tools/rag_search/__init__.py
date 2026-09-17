"""
rag_search follow-up: inject RAG context for the parser query.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import JsonValue, TypeAdapter, ValidationError

from agents.chat.agent_workflow import (
    RAG_SEARCH_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.roles import WORKFLOW_DESIGNER_ROLE_ID, get_role
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.rag_search.follow_ups import (
    RAG_SEARCH_FOLLOW_UP_PREFIX,
    RAG_SEARCH_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import (
    FollowUpContribution,
    LanguageHintGetter,
    ParserOutput,
)
from core.schemas.primitives import WorkflowInputs

EXECUTION_TIMEOUT_S: float = 120.0


def _empty_rag_search_contribution(
    hint: LanguageHintGetter,
) -> FollowUpContribution:
    language = hint()

    chunk = (
        RAG_SEARCH_FOLLOW_UP_PREFIX
        + TOOL_EMPTY_RESULT_LINE
        + RAG_SEARCH_FOLLOW_UP_SUFFIX.format(
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


def _extract_result(output: object) -> tuple[str, str]:
    if not isinstance(output, Mapping):
        return "", ""

    raw_data = output.get("data")
    raw_error = output.get("error")

    data = ""
    error = ""

    if raw_data is not None:
        data = str(raw_data).strip()

    if isinstance(raw_error, Mapping):
        if "error" in raw_error:
            raw_error = raw_error["error"]
        elif "message" in raw_error:
            raw_error = raw_error["message"]

    if raw_error is not None:
        error = str(raw_error).strip()

    return data, error


def _build_unit_param_overrides(ctx: ExecutionFollowUpContext) -> dict[str, Any]:
    agent_for_rag = (
        getattr(ctx, "agent_role_id", None)
        or WORKFLOW_DESIGNER_ROLE_ID
    )

    role_config = get_role(agent_for_rag)
    rag_params: dict[str, Any] = (
        getattr(role_config, "extra", None) or {}
    ).get("rag", {}) or {}

    unit_param_overrides: dict[str, Any] = {}

    rag_search_override: dict[str, Any] = {}

    top_k = rag_params.get("top_k")
    min_score = rag_params.get("min_score")

    if top_k is not None:
        rag_search_override["top_k"] = str(top_k)

    if min_score is not None:
        rag_search_override["min_score"] = str(min_score)

    if rag_search_override:
        unit_param_overrides["rag_search"] = rag_search_override

    format_rag_override: dict[str, Any] = {}

    format_max_chars = rag_params.get("format_max_chars")
    format_snippet_max = rag_params.get("format_snippet_max")

    if format_max_chars is not None:
        format_rag_override["max_chars"] = str(format_max_chars)

    if format_snippet_max is not None:
        format_rag_override["snippet_max"] = str(format_snippet_max)

    if format_rag_override:
        unit_param_overrides["format_rag"] = format_rag_override

    return unit_param_overrides


async def run_rag_search_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    # Keep this import local to avoid the action-block/follow-up import cycle.
    from agents.tools.rag_search.action_block import SearchActionBlock

    try:
        ctx.set_inline_status("Searching the knowledge base…")
    except (AttributeError, TypeError):
        pass

    hint = language_hint

    try:
        search_actions = po.actions.get_tool_actions("search")

        if not search_actions:
            raise ValueError(
                "RAG-search follow-up was requested, but no "
                "search action was found"
            )

        if len(search_actions) != 1:
            raise ValueError(
                "RAG-search follow-up expected exactly one search action, "
                f"got {len(search_actions)}"
            )

        raw_action = search_actions[0]

        # Validate and normalize parser output using the authoritative schema.
        try:
            action = SearchActionBlock.model_validate(raw_action)
        except ValidationError as exc:
            try:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(
                        "Invalid search action: "
                        f"{str(exc)[:120]}"
                    )
            except (AttributeError, TypeError):
                pass

            raise

        payload: JsonValue = TypeAdapter(JsonValue).validate_python(
            action.model_dump(mode="json")
        )

        edits: JsonValue = [payload]

        initial_inputs: WorkflowInputs = {
            "rag_search": {
                "edits": edits,
            }
        }

        out, errs = await run_workflow_with_errors(
            RAG_SEARCH_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            unit_param_overrides=_build_unit_param_overrides(ctx),
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )


        if errs:
            error_text = _format_workflow_error(errs)

            try:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(f"RAG search error: {error_text}")
            except (AttributeError, TypeError):
                pass

        format_rag_output: object = {}

        if isinstance(out, Mapping):
            format_rag_output = out.get("format_rag") or {}

        result_data, result_error = _extract_result(format_rag_output)

        # Prefer an explicit error returned by the workflow.
        result = result_error or result_data

        if not result:
            return _empty_rag_search_contribution(hint)

        language = hint()

        chunk = (
            RAG_SEARCH_FOLLOW_UP_PREFIX
            + result
            + RAG_SEARCH_FOLLOW_UP_SUFFIX.format(
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
                await ctx.toast("RAG search operation timed out")
        except (AttributeError, TypeError):
            pass

        return _empty_rag_search_contribution(hint)

    except ValidationError:
        raise

    except (AttributeError, TypeError, KeyError, ValueError, IndexError) as exc:
        try:
            if ctx.is_current_run(ctx.token):
                await ctx.toast(
                    "RAG search workflow crashed: "
                    f"{type(exc).__name__}: {str(exc)[:120]}"
                )
        except (AttributeError, TypeError):
            pass

        raise


__all__ = ["run_rag_search_follow_up"]
