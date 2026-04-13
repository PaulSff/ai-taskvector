"""
read_code_block follow-up: todos + validate canvas graph, then ``read_code_block_follow_up_workflow.json``.
Lookup adds registry paths; **PayloadTransform.repeat_for_each** builds **Chameleon** ``actions`` from
``implementation_source_paths``; **Router** gates on ``needs_implementation_links``; **Chameleon** runs
``RunWorkflow`` → ``rag_context_workflow`` once per path.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from assistants.tools.read_code_block.follow_ups import (
    READ_CODE_BLOCK_FOLLOW_UP_PREFIX,
    READ_CODE_BLOCK_FOLLOW_UP_SUFFIX,
)
from assistants.tools.types import (
    FOLLOW_UP_EXTRA_IMPLEMENTATION_LINK_TYPES,
    FOLLOW_UP_EXTRA_READ_CODE_IDS,
    FollowUpContribution,
)
from assistants.tools.workflow_path import get_tool_workflow_path
from gui.flet.components.workflow.core_workflows import (
    validate_graph_to_apply_for_canvas,
)


def _rag_excerpt_blocks_from_chameleon(ch_out: Any, paths: list[str]) -> list[str]:
    """Build ``--- path ---\\n<text>`` blocks from Chameleon step outputs (nested ``format_rag.data``)."""
    steps = (ch_out or {}).get("data") if isinstance(ch_out, dict) else None
    if not isinstance(steps, list):
        return []
    parts: list[str] = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict) or step.get("error"):
            continue
        outs = step.get("outputs")
        if not isinstance(outs, dict):
            continue
        fr = outs.get("format_rag")
        if not isinstance(fr, dict):
            continue
        t = str(fr.get("data") or "").strip()
        if not t:
            continue
        label = paths[i] if i < len(paths) else f"step_{i}"
        parts.append(f"--- {label} ---\n{t}")
    return parts


def _run_read_code_block_follow_up_workflow(
    graph_dict: dict[str, Any],
    unit_ids: list[str],
    session_language: str,
) -> dict[str, Any]:
    """Run the full read_code_block follow-up graph; returns executor outputs dict."""
    from runtime.run import run_workflow

    wf = get_tool_workflow_path("read_code_block")
    if not wf.is_file():
        raise FileNotFoundError(f"read_code_block tool workflow not found: {wf}")
    try:
        from units.data_bi import register_data_bi_units

        register_data_bi_units()
    except Exception:
        pass
    return run_workflow(
        wf,
        initial_inputs={
            "inject_graph": {"data": graph_dict},
            "inject_meta": {
                "data": {
                    "read_code_block_ids": list(unit_ids),
                    "session_language": session_language,
                }
            },
        },
        format="dict",
    )


def _impl_types_from_follow_up_out(out: dict[str, Any]) -> list[str]:
    data = (out.get("lookup_graph_units") or {}).get("data")
    if not isinstance(data, dict):
        raise RuntimeError(
            "read_code_block follow-up: expected executor output lookup_graph_units.data to be a dict, "
            f"got {type(data).__name__}"
        )
    raw = data.get("canonical_types_without_code_block")
    if raw is None:
        raise RuntimeError(
            "read_code_block follow-up: lookup_graph_units.data missing key "
            "'canonical_types_without_code_block'"
        )
    if not isinstance(raw, list):
        raise RuntimeError(
            "read_code_block follow-up: canonical_types_without_code_block must be a list, "
            f"got {type(raw).__name__}"
        )
    return [str(x) for x in raw if str(x).strip()]


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

        lang = (hint() or "English").strip() or "English"
        try:
            out = await asyncio.to_thread(
                _run_read_code_block_follow_up_workflow,
                graph_for_cb,
                ids,
                lang,
            )
            impl_types = _impl_types_from_follow_up_out(out)
        except Exception as e:
            try:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(f"read_code_block lookup failed: {e!s}"[:160])
            except Exception:
                pass
            raise
        if impl_types:
            lu_data = (out.get("lookup_graph_units") or {}).get("data")
            paths = (
                lu_data.get("implementation_source_paths")
                if isinstance(lu_data, dict)
                else None
            )
            if not isinstance(paths, list):
                paths = []
            paths = [str(p).strip() for p in paths if p is not None and str(p).strip()]

            rag_parts = _rag_excerpt_blocks_from_chameleon(out.get("chameleon_rag"), paths)
            reg_note = (
                f" No graph code_block for the requested id(s); registry type(s) "
                f"{', '.join(impl_types)} have read_file paths "
                "highlighted in the Units Library on this turn only."
            )
            if rag_parts:
                reg_note += "\n\nKnowledge base excerpts:\n\n" + "\n\n".join(rag_parts)
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
