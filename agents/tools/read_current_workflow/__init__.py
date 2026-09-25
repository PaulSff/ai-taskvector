"""
read_current_workflow follow-up: inject a full graph_summary
(structure + code blocks policy) into follow_up_context.
"""

from __future__ import annotations

import asyncio
import json

from agents.chat.context.follow_up_context import ExecutionFollowUpContext
from agents.chat.context.todo_list_manager import get_summary_params
from agents.tools.read_current_workflow.follow_ups import (
    READ_CURRENT_WORKFLOW_FOLLOW_UP_PREFIX,
    READ_CURRENT_WORKFLOW_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import FollowUpContribution, LanguageHintGetter, ParserOutput
from config.settings import get_coding_is_allowed
from core.graph.summary import graph_summary


async def run_read_current_workflow_follow_up(
    ctx: ExecutionFollowUpContext,
    po: ParserOutput,
    *,
    language_hint: LanguageHintGetter,
) -> FollowUpContribution:
    if not po.actions.tool_actions.get("read_current_workflow"):
        return FollowUpContribution(
            context_chunks=[],
            any_empty_tool=False,
        )

    ctx.set_inline_status("Reading full graph summary…")

    lang = (language_hint() or "English").strip() or "English"

    if not ctx.graph_ref or ctx.graph_ref[0] is None:
        chunk = (
            READ_CURRENT_WORKFLOW_FOLLOW_UP_PREFIX
            + "(No graph loaded; nothing to summarize.)\n"
            + READ_CURRENT_WORKFLOW_FOLLOW_UP_SUFFIX.format(
                language=lang,
                session_language=lang,
            )
        )
        return FollowUpContribution(
            context_chunks=[chunk],
            any_empty_tool=True,
        )

    graph = ctx.graph_ref[0]

    def _build_summary_text() -> str:
        params = get_summary_params(
            get_coding_is_allowed(),
            graph,
        )

        ids = params.get("include_source_for_unit_ids")
        source_ids: list[str] | None = None

        if isinstance(ids, list):
            source_ids = [
                item for item in ids
                if isinstance(item, str)
            ] or None

        summary = graph_summary(
            graph,
            include_structure=True,
            include_code_block_source=bool(
                params.get("include_code_block_source")
            ),
            include_source_for_unit_ids=source_ids,
        )

        return json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        )

    body = await asyncio.to_thread(_build_summary_text)

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

    return FollowUpContribution(
        context_chunks=[chunk],
        any_empty_tool=False,
    )


__all__ = ["run_read_current_workflow_follow_up"]
