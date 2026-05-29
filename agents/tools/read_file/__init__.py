"""
read_file follow-up: single ``read_file_workflow.json`` (Router → PayloadTransform → RunWorkflow ×2).
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from agents.roles import WORKFLOW_DESIGNER_ROLE_ID
from agents.tools.follow_up_common import TOOL_EMPTY_RESULT_LINE
from agents.tools.read_file.follow_ups import (
    REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX,
    REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX,
)
from agents.tools.types import FollowUpContribution
from agents.tools.workflow_path import get_tool_workflow_path


def _text_from_inner_outputs(inner: dict[str, Any]) -> str:
    """Pull formatted RAG text and/or doc_to_text tables from one nested executor output dict."""
    bits: list[str] = []
    fr = inner.get("format_rag")
    if isinstance(fr, dict):
        d = fr.get("data")
        if isinstance(d, str) and d.strip():
            bits.append(d.strip())
    tt = inner.get("tables_to_text")
    if isinstance(tt, dict):
        t = tt.get("text")
        if isinstance(t, str) and t.strip():
            bits.append(
                "--- Tables (doc_to_text: LoadDocument → TablesToText) ---\n"
                + t.strip()
            )
    if not bits:
        pr = inner.get("prompt")
        if isinstance(pr, dict):
            sp = pr.get("system_prompt")
            if isinstance(sp, str) and sp.strip():
                bits.append(sp.strip())
    return "\n\n".join(bits)


def _text_from_read_file_workflow_outputs(
    outputs: dict[str, Any], slot_name: str = "rw_run"
) -> str:
    """
    Extract and return cleaned text from a single workflow output slot (default "rw_run").
    Skips the slot if it's missing, not a dict, has a non-empty string 'error', or its 'data' is not a dict.
    """
    slot = outputs.get(slot_name)
    if not isinstance(slot, dict):
        return ""

    err = slot.get("error")
    if isinstance(err, str) and err.strip():
        return ""

    inner = slot.get("data")
    if not isinstance(inner, dict):
        return ""

    s = _text_from_inner_outputs(inner)
    return (s or "").strip()


def _run_read_file_workflow_for_path(path: str) -> str:
    """Execute read_file orchestration graph for one path; return combined text or \"\"."""
    p = (path or "").strip()
    if not p:
        return ""
    try:
        from runtime.run import run_workflow

        wf = get_tool_workflow_path("read_file")
        if not wf.is_file():
            return ""
        out = run_workflow(
            wf,
            initial_inputs={"inject_path": {"data": p}},  # send just the path string
            format="dict",
        )
        if not isinstance(out, dict):
            return ""
        return _text_from_read_file_workflow_outputs(out)
    except Exception:
        return ""


async def run_read_file_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    """
    Build follow-up context for parser ``read_file`` paths via ``read_file_workflow.json``.
    ``ctx`` may provide ``set_inline_status`` (optional).
    """
    try:
        setter = getattr(ctx, "set_inline_status", None)
        if callable(setter):
            setter("Reading file…")
    except Exception:
        pass
    hint = language_hint
    try:
        paths = po.get("read_file") or []
        if not isinstance(paths, list):
            paths = []
        _ = (
            str(
                getattr(ctx, "agent_role_id", None)
                or getattr(ctx, "agent_label", "")
                or WORKFLOW_DESIGNER_ROLE_ID
            ).strip()
            or WORKFLOW_DESIGNER_ROLE_ID
        )
        parts: list[str] = []
        for path in paths:
            if not isinstance(path, str) or not path.strip():
                continue
            path = path.strip()
            block = await asyncio.to_thread(_run_read_file_workflow_for_path, path)
            if block.strip():
                parts.append(f"--- {path} ---\n{block.strip()}")
        if parts:
            chunk = (
                REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX
                + "\n\n".join(parts)
                + REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            )
            return FollowUpContribution(context_chunks=[chunk], any_empty_tool=False)
        return FollowUpContribution(
            context_chunks=[
                REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX
                + TOOL_EMPTY_RESULT_LINE
                + REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            ],
            any_empty_tool=True,
        )
    except Exception:
        return FollowUpContribution(
            context_chunks=[
                REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX
                + TOOL_EMPTY_RESULT_LINE
                + REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX.format(
                    language=hint(),
                    session_language=hint(),
                )
            ],
            any_empty_tool=True,
        )


__all__ = ["run_read_file_follow_up"]
