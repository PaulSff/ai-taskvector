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
    language: str,
) -> FollowUpContribution:
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


async def _run_single_rag_search(
    ctx: ExecutionFollowUpContext,
    raw_action: object,
    *,
    language: str,
    search_index: int,
) -> FollowUpContribution:
    """
    Execute one validated RAG search.

    This function is intentionally independent of the other searches so it
    can safely be run concurrently with asyncio.gather().
    """
    from agents.tools.rag_search.action_block import SearchActionBlock

    operation_id = uuid4().hex[:10]

    try:
        action = SearchActionBlock.model_validate(raw_action)
    except ValidationError as exc:
        await _safe_toast(
            ctx,
            f"Invalid search action #{search_index + 1}: "
            f"{str(exc)[:120]}",
        )
        raise

    payload: JsonValue = TypeAdapter(JsonValue).validate_python(
        action.model_dump(mode="json")
    )

    initial_inputs: WorkflowInputs = {
        "rag_search": {
            "edits": [payload],
        }
    }

    unit_param_overrides = _build_unit_param_overrides(ctx)

    logger.info(
        "RAG search starting index=%d operation_id=%s",
        search_index,
        operation_id,
    )

    try:
        out, errs = await run_workflow_with_errors(
            RAG_SEARCH_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        logger.info(
            "RAG search completed index=%d operation_id=%s errors=%d",
            search_index,
            operation_id,
            len(errs),
        )

        if errs:
            error_text = _format_workflow_error(errs)

            await _safe_toast(
                ctx,
                f"RAG search #{search_index + 1} error "
                f"({operation_id}): {error_text}",
            )

        format_rag_output: object = {}

        if isinstance(out, Mapping):
            format_rag_output = out.get("format_rag") or {}

        result_data, result_error = _extract_result(format_rag_output)
        result = result_error or result_data

        if not result:
            logger.info(
                "RAG search returned no result index=%d operation_id=%s",
                search_index,
                operation_id,
            )
            return _empty_rag_search_contribution(language)

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
        logger.info(
            "RAG search cancelled index=%d operation_id=%s",
            search_index,
            operation_id,
        )
        raise

    except TimeoutError:
        logger.warning(
            "RAG search timed out index=%d operation_id=%s",
            search_index,
            operation_id,
        )

        await _safe_toast(
            ctx,
            f"RAG search #{search_index + 1} timed out "
            f"({operation_id})",
        )

        return _empty_rag_search_contribution(language)

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
            "RAG search crashed index=%d operation_id=%s error_type=%s",
            search_index,
            operation_id,
            type(exc).__name__,
        )

        await _safe_toast(
            ctx,
            f"RAG search #{search_index + 1} crashed: "
            f"{type(exc).__name__}: {str(exc)[:120]}",
        )

        raise


async def run_rag_search_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    """
    Execute all parser-produced RAG searches concurrently.

    asyncio.gather() preserves input order in its returned result list, so
    context chunks remain ordered consistently with the parser actions.
    """
    language = language_hint()

    search_actions = po.actions.get_tool_actions("search")

    if not search_actions:
        raise ValueError(
            "RAG-search follow-up was requested, but no "
            "search action was found"
        )

    _safe_set_status(
        ctx,
        f"Searching the knowledge base… "
        f"({len(search_actions)} searches)",
    )

    logger.info(
        "Starting concurrent RAG searches count=%d",
        len(search_actions),
    )

    contributions = await asyncio.gather(
        *(
            _run_single_rag_search(
                ctx,
                raw_action,
                language=language,
                search_index=index,
            )
            for index, raw_action in enumerate(search_actions)
        )
    )

    context_chunks = [
        chunk
        for contribution in contributions
        for chunk in contribution.context_chunks
    ]

    return FollowUpContribution(
        context_chunks=context_chunks,
        any_empty_tool=any(
            contribution.any_empty_tool
            for contribution in contributions
        ),
    )


__all__ = ["run_rag_search_follow_up"]
