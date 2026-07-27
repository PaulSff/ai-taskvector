"""rag_search follow-up: inject RAG context for the parser query."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agents.chat.agent_workflow import (
    RAG_SEARCH_WORKFLOW_PATH,
    run_workflow_with_errors,
)
from agents.roles import WORKFLOW_DESIGNER_ROLE_ID, get_role
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.rag_search.follow_ups import (
    RAG_SEARCH_FOLLOW_UP_PREFIX,
    RAG_SEARCH_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import FollowUpContribution

EXECUTION_TIMEOUT_S: float = 120.0


async def run_rag_search_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    try:
        ctx.set_inline_status("Searching the knowledge base…")
    except (AttributeError, TypeError):
        pass

    chunk_ws: str | None = None
    hint = language_hint

    try:
        # Mandatory payload
        edits = po.get("edits")
        if not isinstance(edits, list) or not edits:
            chunk_ws = (
                RAG_SEARCH_FOLLOW_UP_PREFIX
                + TOOL_EMPTY_RESULT_LINE
                + RAG_SEARCH_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
            return FollowUpContribution(context_chunks=[chunk_ws], any_empty_tool=True)

        # Role comes from ctx (fallback to workflow designer)
        agent_for_rag = getattr(ctx, "agent_role_id", None) or WORKFLOW_DESIGNER_ROLE_ID
        role_config = get_role(agent_for_rag)

        # RoleConfig stores knobs in .extra
        rag_params: dict[str, Any] = (role_config.extra or {}).get("rag", {}) or {}

        # Map role rag params -> overrides (no hardcoding)
        top_k = rag_params.get("top_k")  # -> unit override "top_k"
        min_score = rag_params.get("min_score")
        format_max_chars = rag_params.get("format_max_chars")
        format_snippet_max = rag_params.get("format_snippet_max")

        unit_param_overrides: dict[str, Any] = {}

        # Overrides for rag_search unit
        rag_search_override: dict[str, Any] = {}
        if top_k is not None:
            rag_search_override["top_k"] = str(top_k)
        if min_score is not None:
            rag_search_override["min_score"] = str(min_score)
        if rag_search_override:
            unit_param_overrides["rag_search"] = rag_search_override

        # Overrides for format_rag unit
        format_rag_override: dict[str, Any] = {}
        if format_max_chars is not None:
            format_rag_override["max_chars"] = str(format_max_chars)
        if format_snippet_max is not None:
            format_rag_override["snippet_max"] = str(format_snippet_max)
        if format_rag_override:
            unit_param_overrides["format_rag"] = format_rag_override

        initial_inputs = {"rag_search": {"edits": edits}}

        out, errs = await run_workflow_with_errors(
            RAG_SEARCH_WORKFLOW_PATH,
            initial_inputs=initial_inputs,
            unit_param_overrides=unit_param_overrides,
            format="dict",
            execution_timeout_s=EXECUTION_TIMEOUT_S,
        )

        if errs:
            try:
                await ctx.toast(f"RAG search error: {errs[0][1][:120]}")
            except (AttributeError, TypeError, IndexError):
                pass

        # Output from format_rag data port
        res = (out or {}).get("format_rag", {}).get("data") or ""
        if res.strip():
            chunk_ws = (
                RAG_SEARCH_FOLLOW_UP_PREFIX
                + res
                + RAG_SEARCH_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )

    except (KeyError, TypeError, ValueError) as e:
        try:
            await ctx.toast(
                f"RAG search workflow crashed: {type(e).__name__}: {str(e)[:120]}"
            )
        except (AttributeError, TypeError):
            pass

    if not chunk_ws:
        chunk_ws = (
            RAG_SEARCH_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + RAG_SEARCH_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        return FollowUpContribution(context_chunks=[chunk_ws], any_empty_tool=True)

    return FollowUpContribution(context_chunks=[chunk_ws], any_empty_tool=False)


__all__ = ["run_rag_search_follow_up"]
