"""rag_search follow-up: inject RAG context for the parser query."""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from assistants.tools.rag_search.follow_ups import (
    RAG_SEARCH_FOLLOW_UP_PREFIX,
    RAG_SEARCH_FOLLOW_UP_SUFFIX,
)
from assistants.tools.types import FollowUpContribution
from gui.flet.chat_with_the_assistants.rag_context import get_rag_context


async def run_rag_search_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    try:
        ctx.set_inline_status("Searching knowledge base…")
    except Exception:
        pass
    hint = language_hint
    try:
        rag_ctx = await asyncio.to_thread(
            get_rag_context,
            po["rag_search"],
            "Workflow Designer",
            po.get("rag_search_max_results"),
            po.get("rag_search_max_chars"),
            po.get("rag_search_snippet_max"),
        )
    except Exception:
        rag_ctx = ""
    rag_text = (
        rag_ctx.strip()
        if isinstance(rag_ctx, str)
        else str(rag_ctx or "").strip()
    )
    if not rag_text:
        rag_text = "(No relevant RAG context returned.)"
    chunk = (
        RAG_SEARCH_FOLLOW_UP_PREFIX
        + rag_text
        + RAG_SEARCH_FOLLOW_UP_SUFFIX.format(
            language=hint(),
            session_language=hint(),
        )
    )
    return FollowUpContribution(context_chunks=[chunk], any_empty_tool=False)


__all__ = ["run_rag_search_follow_up"]
