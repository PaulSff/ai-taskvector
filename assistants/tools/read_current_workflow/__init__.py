"""
read_current_workflow follow-up: inject a **full** ``graph_summary`` (structure + code blocks policy)
into ``follow_up_context``, same orchestration as RAG/search (no separate tool workflow run).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from assistants.tools.read_current_workflow.follow_ups import (
    READ_CURRENT_WORKFLOW_FOLLOW_UP_PREFIX,
    READ_CURRENT_WORKFLOW_FOLLOW_UP_SUFFIX,
)
from assistants.tools.types import FollowUpContribution
from core.graph.summary import graph_summary
from gui.chat.context.todo_list_manager import get_summary_params
from gui.components.settings import get_coding_is_allowed


def _graph_to_dict(graph_ref: Any) -> dict[str, Any]:
    if graph_ref is None:
        return {}
    if hasattr(graph_ref, "model_dump"):
        return graph_ref.model_dump(by_alias=True)
    return graph_ref if isinstance(graph_ref, dict) else {}


async def run_read_current_workflow_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    if not po.get("read_current_workflow"):
        return FollowUpContribution(context_chunks=[], any_empty_tool=False)

    try:
        ctx.set_inline_status("Reading full graph summary…")
    except Exception:
        pass

    hint = language_hint
    lang = (hint() or "English").strip() or "English"

    if not ctx.graph_ref or ctx.graph_ref[0] is None:
        chunk = (
            READ_CURRENT_WORKFLOW_FOLLOW_UP_PREFIX
            + "(No graph loaded in the designer; nothing to summarize.)\n"
            + READ_CURRENT_WORKFLOW_FOLLOW_UP_SUFFIX.format(
                language=lang,
                session_language=lang,
            )
        )
        return FollowUpContribution(context_chunks=[chunk], any_empty_tool=True)

    g_dict = _graph_to_dict(ctx.graph_ref[0])

    def _build_summary_text() -> str:
        params = get_summary_params(get_coding_is_allowed(), g_dict)
        ids = params.get("include_source_for_unit_ids")
        summ = graph_summary(
            g_dict,
            include_structure=True,
            include_code_block_source=bool(params.get("include_code_block_source")),
            include_source_for_unit_ids=list(ids) if isinstance(ids, list) and ids else None,
        )
        return json.dumps(summ, indent=2, ensure_ascii=False)

    try:
        body = await asyncio.to_thread(_build_summary_text)
    except Exception as ex:
        body = f"(Failed to build graph summary: {ex})"

    chunk = (
        READ_CURRENT_WORKFLOW_FOLLOW_UP_PREFIX
        + "```json\n"
        + body
        + "\n```\n"
        + READ_CURRENT_WORKFLOW_FOLLOW_UP_SUFFIX.format(
            language=lang,
            session_language=lang,
        )
    )
    return FollowUpContribution(context_chunks=[chunk], any_empty_tool=False)


__all__ = ["run_read_current_workflow_follow_up"]
