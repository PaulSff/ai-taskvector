"""
read_code_block follow-up: todo/graph updates + optional RAG for registry types missing code_blocks.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from assistants.skills.read_code_block.follow_ups import (
    READ_CODE_BLOCK_FOLLOW_UP_PREFIX,
    READ_CODE_BLOCK_FOLLOW_UP_SUFFIX,
)
from assistants.skills.read_code_block.graph_unit_helpers import unit_types_missing_code_blocks
from assistants.skills.types import (
    FOLLOW_UP_EXTRA_IMPLEMENTATION_LINK_TYPES,
    FOLLOW_UP_EXTRA_READ_CODE_IDS,
    FollowUpContribution,
)
from gui.flet.chat_with_the_assistants.rag_context import get_rag_context_by_path
from gui.flet.components.workflow.core_workflows import (
    run_graph_summary,
    run_units_library_source_paths,
    validate_graph_to_apply_for_canvas,
)


async def run_read_code_block_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    ids = list(po.get("read_code_block_ids") or [])
    hint = language_hint
    impl_types: list[str] = []
    chunks: list[str] = []

    def _extra() -> dict[str, Any]:
        return {
            FOLLOW_UP_EXTRA_READ_CODE_IDS: list(ids),
            FOLLOW_UP_EXTRA_IMPLEMENTATION_LINK_TYPES: list(impl_types),
        }

    if ctx.graph_ref[0]:
        try:
            ctx.set_inline_status("Adding task and re-running…")
        except Exception:
            pass
        from gui.flet.chat_with_the_assistants.todo_list_manager import add_tasks_for_read_code_block

        _g = ctx.graph_ref[0]
        _g_dict = _g.model_dump(by_alias=True) if hasattr(_g, "model_dump") else (_g if isinstance(_g, dict) else _g)
        updated = add_tasks_for_read_code_block(ids, _g_dict)
        graph_for_cb: dict[str, Any] = {}
        if isinstance(updated, dict):
            graph_for_cb = updated
        elif hasattr(updated, "model_dump"):
            graph_for_cb = updated.model_dump(by_alias=True)
        if hasattr(ctx.graph_ref[0], "model_dump"):
            vg, v_err = validate_graph_to_apply_for_canvas(updated)
            if v_err or vg is None:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(f"Graph validation failed: {(v_err or '')[:120]}")
            else:
                ctx.graph_ref[0] = vg
                graph_for_cb = vg.model_dump(by_alias=True)
        else:
            ctx.graph_ref[0] = updated
            if isinstance(updated, dict):
                graph_for_cb = updated
        impl_types = unit_types_missing_code_blocks(graph_for_cb, ids)
        if impl_types:
            paths = run_units_library_source_paths(
                run_graph_summary(graph_for_cb),
                impl_types,
            )
            rag_parts: list[str] = []
            for path in paths:
                c = await asyncio.to_thread(
                    get_rag_context_by_path,
                    path,
                    "Workflow Designer",
                )
                if c and c.strip():
                    rag_parts.append(f"--- {path} ---\n{c.strip()}")
            reg_note = (
                f" No graph code_block for the requested id(s); registry type(s) "
                f"{', '.join(impl_types)} have read_file paths "
                "highlighted in the Units Library on this turn only."
            )
            if rag_parts:
                reg_note += "\n\nKnowledge base excerpts:\n\n" + "\n\n".join(
                    rag_parts
                )
            chunks.append(
                READ_CODE_BLOCK_FOLLOW_UP_PREFIX.rstrip()
                + reg_note
                + "\n"
                + READ_CODE_BLOCK_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
        else:
            chunks.append(
                READ_CODE_BLOCK_FOLLOW_UP_PREFIX.rstrip()
                + " The source for the requested unit(s) is included in the graph summary.\n"
                + READ_CODE_BLOCK_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
    else:
        chunks.append(
            READ_CODE_BLOCK_FOLLOW_UP_PREFIX.rstrip()
            + " No graph is loaded in the designer; unit source cannot be read from the graph until a graph is available.\n"
            + READ_CODE_BLOCK_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )

    return FollowUpContribution(context_chunks=chunks, any_empty_tool=False, extra=_extra())


__all__ = ["run_read_code_block_follow_up"]
