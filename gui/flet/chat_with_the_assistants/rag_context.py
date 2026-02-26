"""
RAG-augmented context for assistants: retrieve relevant workflows, nodes, and documents
and inject them into the prompt for Workflow Designer and RL Coach.
Index update (manifests, MD5, incremental) is in rag.context_updater; Flet calls it at startup.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import flet as ft

RAG_CONTEXT_MAX_CHARS = 2000
RAG_TOP_K = 8

# Repo root (gui/flet/chat_with_the_assistants -> 4 parents)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_UNITS_DIR = _REPO_ROOT / "units"


def get_rag_context(query: str, assistant: str) -> str:
    """
    Retrieve relevant context from the RAG index for the given assistant.
    Returns formatted string to inject into the prompt, or empty string if unavailable.

    Args:
        query: User message (used as search query)
        assistant: "Workflow Designer" or "RL Coach"

    Returns:
        Formatted "Relevant context from knowledge base: ..." block, or ""
    """
    query = (query or "").strip()
    if not query:
        return ""
    try:
        from gui.flet.components.settings import get_rag_embedding_model, get_rag_index_dir
        from rag.indexer import RAGIndex

        index = RAGIndex(
            persist_dir=str(get_rag_index_dir()),
            embedding_model=get_rag_embedding_model(),
        )
    except (ImportError, Exception):
        return ""

    content_type = None
    if assistant == "Workflow Designer":
        content_type = None
    try:
        results = index.search(query, top_k=RAG_TOP_K, content_type=content_type)
    except Exception:
        return ""

    if not results:
        return ""

    parts: list[str] = []
    total = 0
    for r in results:
        meta = r.get("metadata") or {}
        text = (r.get("text") or "").strip()
        if not text:
            continue
        ct = meta.get("content_type", "")
        source = meta.get("file_path") or meta.get("raw_json_path") or meta.get("source") or meta.get("id") or "?"
        label = meta.get("name") or source
        snippet = text.replace("\n", " ")[:300]
        if ct:
            entry = f"[{ct}] {label}: {snippet}"
        else:
            entry = f"{label}: {snippet}"
        if total + len(entry) + 2 > RAG_CONTEXT_MAX_CHARS:
            break
        parts.append(entry)
        total += len(entry) + 2

    if not parts:
        return ""

    block = "Relevant context from knowledge base:\n" + "\n".join(parts)
    block += "\n\nUse file_path, raw_json_path, or id from above for import_workflow / import_unit when applicable."
    return block


async def ensure_units_indexed_at_startup(page: ft.Page) -> None:
    """Run at GUI start: call rag.context_updater, show spinner then toast with status."""
    from gui.flet.tools.notifications import show_toast

    try:
        from gui.flet.components.settings import get_rag_embedding_model, get_rag_index_dir
        from rag.context_updater import need_indexing, run_update
    except ImportError:
        await show_toast(page, "RAG: update not available")
        return

    rag_index_dir = get_rag_index_dir()
    need_units, need_mydata, reason = await asyncio.to_thread(need_indexing, rag_index_dir, _UNITS_DIR)
    if not need_units and not need_mydata:
        await show_toast(page, f"RAG: {reason}")
        return

    progress_overlay = ft.Stack(
        expand=True,
        controls=[
            ft.Container(
                content=ft.Row(
                    [
                        ft.ProgressRing(width=24, height=24, stroke_width=2),
                        ft.Text("RAG: indexing...", size=12, color=ft.Colors.GREY_400),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=12,
                ),
                left=0,
                right=0,
                top=20,
            ),
        ],
    )
    page.overlay.append(progress_overlay)
    page.update()

    try:
        result = await asyncio.to_thread(
            run_update,
            rag_index_dir,
            _UNITS_DIR,
            embedding_model=get_rag_embedding_model(),
        )
    finally:
        if progress_overlay in page.overlay:
            page.overlay.remove(progress_overlay)
            page.update()

    if result.get("error"):
        await show_toast(page, result["error"])
    else:
        await show_toast(page, result.get("message", result.get("details", "RAG: ok")))
