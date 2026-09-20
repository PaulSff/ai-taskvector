"""
rag_search follow-up: inject RAG context for the parser query.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from uuid import uuid4

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
from core.schemas.primitives import JsonObject, WorkflowInputs

logger = logging.getLogger(__name__)

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


def _build_unit_param_overrides(
    ctx: ExecutionFollowUpContext,
) -> WorkflowInputs:
    agent_for_rag = (
        getattr(ctx, "agent_role_id", None)
        or WORKFLOW_DESIGNER_ROLE_ID
    )

    role_config = get_role(agent_for_rag)

    rag_params: JsonObject = (
        getattr(role_config, "extra", None) or {}
    ).get("rag", {}) or {}

    unit_param_overrides: WorkflowInputs = {}

    rag_search_override: JsonObject = {}

    top_k = rag_params.get("top_k")
    min_score = rag_params.get("min_score")

    if top_k is not None:
        rag_search_override["top_k"] = str(top_k)

    if min_score is not None:
        rag_search_override["min_score"] = str(min_score)

    if rag_search_override:
        unit_param_overrides["rag_search"] = rag_search_override

    format_rag_override: JsonObject = {}

    format_max_chars = rag_params.get("format_max_chars")
    format_snippet_max = rag_params.get("format_snippet_max")

    if format_max_chars is not None:
        format_rag_override["max_chars"] = str(format_max_chars)

    if format_snippet_max is not None:
        format_rag_override["snippet_max"] = str(format_snippet_max)

    if format_rag_override:
        unit_param_overrides["format_rag"] = format_rag_override

    return unit_param_overrides



def _is_current_run(ctx: ExecutionFollowUpContext) -> bool:
    """
    A failed or stale UI update must never break the search itself.

    The context API may not provide is_current_run() in every test or
    lightweight implementation, so absence is treated as current.
    """
    try:
        is_current_run = getattr(ctx, "is_current_run", None)

        if is_current_run is None:
            return True

        return bool(is_current_run(ctx.token))

    except (AttributeError, TypeError):
        return True


async def _safe_toast(
    ctx: ExecutionFollowUpContext,
    message: str,
) -> None:
    """
    Toast only for the active run.

    This prevents an older concurrent search from displaying an error after
    a newer search has already become the active run.
    """
    if not _is_current_run(ctx):
        return

    try:
        await ctx.toast(message)
    except (AttributeError, TypeError):
        pass


def _safe_set_status(
    ctx: ExecutionFollowUpContext,
    message: str,
) -> None:
    if not _is_current_run(ctx):
        return

    try:
        ctx.set_inline_status(message)
    except (AttributeError, TypeError):
        pass


async def run_rag_search_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    """
    Run one independent RAG search.

    This function is safe to invoke concurrently as long as
    run_workflow_with_errors() does not store per-execution state globally.
    """
    # Keep this import local to avoid the action-block/follow-up import cycle.
    from agents.tools.rag_search.action_block import SearchActionBlock

    operation_id = uuid4().hex[:10]

    # Snapshot this once. Calling a mutable context-backed hint multiple times
    # could otherwise produce mixed-language output.
    language = language_hint()

    logger.info(
        "RAG search started operation_id=%s",
        operation_id,
    )

    _safe_set_status(
        ctx,
        f"Searching the knowledge base… ({operation_id})",
    )

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

        try:
            action = SearchActionBlock.model_validate(raw_action)
        except ValidationError as exc:
            await _safe_toast(
                ctx,
                f"Invalid search action: {str(exc)[:120]}",
            )
            raise

        payload: JsonValue = TypeAdapter(JsonValue).validate_python(
            action.model_dump(mode="json")
        )

        # This list is created per invocation and must not be reused across
        # concurrent workflow executions.
        edits: JsonValue = [payload]

        initial_inputs: WorkflowInputs = {
            "rag_search": {
                "edits": edits,
            }
        }

        # Also created per invocation. The workflow runner must not mutate and
        # retain this object after the call completes.
        unit_param_overrides = _build_unit_param_overrides(ctx)

        logger.info(
            "RAG workflow starting operation_id=%s",
            operation_id,
        )

        out, errs = await run_workflow_with_errors(
            RAG_SEARCH_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        logger.info(
            "RAG workflow completed operation_id=%s errors=%d output_type=%s",
            operation_id,
            len(errs),
            type(out).__name__,
        )

        if errs:
            error_text = _format_workflow_error(errs)

            await _safe_toast(
                ctx,
                f"RAG search error ({operation_id}): {error_text}",
            )

        format_rag_output: object = {}

        if isinstance(out, Mapping):
            format_rag_output = out.get("format_rag") or {}

        result_data, result_error = _extract_result(format_rag_output)

        # Preserve the existing behavior: an explicit workflow error wins over
        # returned data.
        result = result_error or result_data

        if not result:
            logger.info(
                "RAG workflow returned no result operation_id=%s",
                operation_id,
            )
            return _empty_rag_search_contribution(
                lambda: language,
            )

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

    except asyncio.CancelledError:
        # Do not convert cancellation into an empty result. The caller needs
        # cancellation to propagate so it can stop the underlying operation.
        logger.info(
            "RAG search cancelled operation_id=%s",
            operation_id,
        )
        raise

    except TimeoutError:
        logger.warning(
            "RAG search timed out operation_id=%s",
            operation_id,
        )

        await _safe_toast(
            ctx,
            f"RAG search operation timed out ({operation_id})",
        )

        return _empty_rag_search_contribution(
            lambda: language,
        )

    except ValidationError:
        raise

    except (
        AttributeError,
        TypeError,
        KeyError,
        ValueError,
        IndexError,
    ) as exc:
        logger.exception(
            "RAG workflow crashed operation_id=%s error_type=%s",
            operation_id,
            type(exc).__name__,
        )

        await _safe_toast(
            ctx,
            "RAG search workflow crashed: "
            f"{type(exc).__name__}: {str(exc)[:120]}",
        )

        raise


__all__ = ["run_rag_search_follow_up"]
