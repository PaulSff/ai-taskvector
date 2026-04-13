"""run_workflow follow-up: surface prior turn run_output to the assistant."""
from __future__ import annotations

import json
from typing import Any, Callable

from assistants.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from assistants.tools.run_workflow.follow_ups import (
    RUN_WORKFLOW_FOLLOW_UP_PREFIX,
    RUN_WORKFLOW_FOLLOW_UP_SUFFIX,
)
from assistants.tools.types import FollowUpContribution


async def run_run_workflow_follow_up(
    ctx: Any,
    _po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    try:
        ctx.set_inline_status("Workflow run result…")
    except Exception:
        pass
    wf = getattr(ctx, "follow_up_source_response", None)
    if not isinstance(wf, dict):
        wf = {}
    hint = language_hint

    if ctx.graph_ref[0]:
        from gui.chat_with_the_assistants.todo_list_manager import add_tasks_for_run_workflow

        _g = ctx.graph_ref[0]
        _g_dict = _g.model_dump(by_alias=True) if hasattr(_g, "model_dump") else (_g if isinstance(_g, dict) else _g)
        updated = add_tasks_for_run_workflow(_g_dict)
        if hasattr(ctx.graph_ref[0], "model_dump"):
            from gui.components.workflow_tab.core_workflows import validate_graph_to_apply_for_canvas

            vg, v_err = validate_graph_to_apply_for_canvas(updated)
            if v_err or vg is None:
                if ctx.is_current_run(ctx.token):
                    await ctx.toast(f"Graph validation failed: {(v_err or '')[:120]}")
            else:
                ctx.graph_ref[0] = vg
        else:
            ctx.graph_ref[0] = updated

    run_out = wf.get("run_output")
    chunk: str | None = None
    if ctx.on_show_run_console and isinstance(run_out, dict):
        try:
            ctx.on_show_run_console(run_out)
        except Exception:
            pass
    if isinstance(run_out, dict):
        data = run_out.get("data")
        err = run_out.get("error")
        parts: list[str] = []
        if data is not None:
            try:
                parts.append(json.dumps(data, indent=2, ensure_ascii=False))
            except Exception:
                parts.append(str(data))
        if isinstance(err, str) and err.strip():
            parts.append(f"Error: {err}")
        if parts:
            chunk = (
                RUN_WORKFLOW_FOLLOW_UP_PREFIX
                + "\n".join(parts)
                + RUN_WORKFLOW_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
    elif run_out is not None:
        chunk = (
            RUN_WORKFLOW_FOLLOW_UP_PREFIX
            + str(run_out)
            + RUN_WORKFLOW_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
    if not chunk:
        chunk = (
            RUN_WORKFLOW_FOLLOW_UP_PREFIX
            + TOOL_EMPTY_RESULT_LINE
            + RUN_WORKFLOW_FOLLOW_UP_SUFFIX.format(
                language=hint(),
                session_language=hint(),
            )
        )
        return FollowUpContribution(context_chunks=[chunk], any_empty_tool=True)
    return FollowUpContribution(context_chunks=[chunk], any_empty_tool=False)


__all__ = ["run_run_workflow_follow_up"]
