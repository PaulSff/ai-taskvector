"""
read_file follow-up: RAG path retrieval + optional .xlsx table extract (doc_to_text workflow).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from assistants.skills.follow_up_common import TOOL_EMPTY_RESULT_LINE
from assistants.skills.read_file.follow_ups import (
    REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX,
    REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX,
)
from assistants.skills.types import FollowUpContribution
from gui.flet.chat_with_the_assistants.rag_context import get_rag_context_by_path

_READ_FILE_XLSX_TABLES_MAX_CHARS = 200_000


def doc_to_text_tables_for_xlsx_path(path_str: str) -> str | None:
    """
    Run doc_to_text workflow for an on-disk .xlsx file.
    Returns tables_to_text ``text`` (CSV-style), or None if not applicable / failed.
    """
    p = Path(path_str).expanduser()
    try:
        p = p.resolve()
    except OSError:
        return None
    if not p.is_file() or p.suffix.lower() != ".xlsx":
        return None
    try:
        from gui.flet.components.settings import get_doc_to_text_workflow_path
        from runtime.run import run_workflow
    except ImportError:
        return None
    wf_path = get_doc_to_text_workflow_path()
    if not wf_path.is_file():
        return None
    try:
        from units.data_bi import register_data_bi_units

        register_data_bi_units()
    except Exception:
        pass
    try:
        outputs = run_workflow(
            wf_path,
            initial_inputs={"inject_path": {"data": str(p)}},
        )
    except Exception:
        return None
    if not isinstance(outputs, dict):
        return None
    load_doc = outputs.get("load_doc")
    if isinstance(load_doc, dict):
        err = load_doc.get("error")
        if isinstance(err, str) and err.strip():
            return None
    tt = outputs.get("tables_to_text")
    if not isinstance(tt, dict):
        return None
    raw = tt.get("text")
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    cap = _READ_FILE_XLSX_TABLES_MAX_CHARS
    if len(text) > cap:
        text = text[:cap] + "\n\n[… truncated spreadsheet tables …]"
    return text


async def run_read_file_follow_up(
    ctx: Any,
    po: dict[str, Any],
    *,
    language_hint: Callable[[], str],
) -> FollowUpContribution:
    """
    Build follow-up context for parser ``read_file`` paths (RAG + .xlsx tables).
    ``ctx`` must provide ``assistant_label`` (str) for RAG; may provide ``set_inline_status`` (optional).
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
        label = str(getattr(ctx, "assistant_label", "") or "Workflow Designer").strip() or "Workflow Designer"
        parts: list[str] = []
        for path in paths:
            if not isinstance(path, str) or not path.strip():
                continue
            path = path.strip()
            c = await asyncio.to_thread(get_rag_context_by_path, path, label)
            block = (c or "").strip()
            tables = await asyncio.to_thread(doc_to_text_tables_for_xlsx_path, path)
            if tables:
                block = (
                    block
                    + "\n\n--- Tables (doc_to_text: LoadDocument → TablesToText) ---\n"
                    + tables
                )
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


__all__ = ["doc_to_text_tables_for_xlsx_path", "run_read_file_follow_up"]
