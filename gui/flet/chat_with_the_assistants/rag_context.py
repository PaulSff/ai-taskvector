"""
RAG-augmented context for assistants: retrieve relevant workflows, nodes, and documents
and inject them into the prompt for Workflow Designer and RL Coach.
Index update (manifests, MD5, incremental) is in rag.context_updater; Flet calls it at startup.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import flet as ft

# Default limits (e.g. for RL Coach or generic use)
RAG_CONTEXT_MAX_CHARS = 2000
RAG_TOP_K = 8

# Tighter limits for Workflow Designer to reduce context overload and keep focus on editing
WORKFLOW_DESIGNER_RAG_MAX_CHARS = 1200
WORKFLOW_DESIGNER_RAG_TOP_K = 4

# Keywords that suggest the user wants import/catalogue/docs (only then inject RAG for Workflow Designer)
_RAG_INTENT_KEYWORDS = (
    "import", "load workflow", "add node", "from catalogue", "from catalog",
    "workflow from", "file path", "node-red", "n8n", "comfy", "pyflow",
    "import_workflow", "import_unit", "request_unit_specs", "wire", "wiring",
    "documentation", "knowledge base", "catalogue", "catalog",
)

# Repo root (gui/flet/chat_with_the_assistants -> 4 parents)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_UNITS_DIR = _REPO_ROOT / "units"


def rag_query_from_graph_origin(graph: Any) -> str:
    """
    Build a RAG search query from the graph origin (node-red, n8n, canonical).
    Used to retrieve relevant conventions/patterns when generating unit docs (augmenter).
    """
    if hasattr(graph, "model_dump"):
        g = graph.model_dump(by_alias=True)
    elif isinstance(graph, dict):
        g = graph
    else:
        return "workflow node API documentation conventions"
    origin = g.get("origin")
    if origin is None:
        return "workflow node API documentation conventions"
    parts: list[str] = []
    if isinstance(origin, dict):
        if origin.get("node_red"):
            parts.append("Node-RED node conventions patterns")
        if origin.get("n8n"):
            parts.append("n8n node structure conventions")
        if origin.get("canonical"):
            parts.append("workflow unit API documentation")
    else:
        if getattr(origin, "node_red", None):
            parts.append("Node-RED node conventions patterns")
        if getattr(origin, "n8n", None):
            parts.append("n8n node structure conventions")
        if getattr(origin, "canonical", None):
            parts.append("workflow unit API documentation")
    if not parts:
        return "workflow node API documentation conventions"
    return " ".join(parts)


def _workflow_designer_wants_rag(query: str) -> bool:
    """Return True if the user message suggests import/catalogue/docs so RAG is relevant."""
    q = (query or "").lower().strip()
    if not q:
        return False
    return any(kw in q for kw in _RAG_INTENT_KEYWORDS)


def get_rag_context(query: str, assistant: str) -> str:
    """
    Retrieve relevant context from the RAG index for the given assistant.
    Returns formatted string to inject into the prompt, or empty string if unavailable.

    For Workflow Designer, RAG is only injected when the query suggests import/catalogue/docs,
    to avoid overwhelming the model and distracting from direct graph edits.

    Args:
        query: User message (used as search query)
        assistant: "Workflow Designer" or "RL Coach"

    Returns:
        Formatted "Relevant context from knowledge base: ..." block, or ""
    """
    query = (query or "").strip()
    if not query:
        return ""
    if assistant == "Workflow Designer" and not _workflow_designer_wants_rag(query):
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
    max_chars = WORKFLOW_DESIGNER_RAG_MAX_CHARS if assistant == "Workflow Designer" else RAG_CONTEXT_MAX_CHARS
    top_k = WORKFLOW_DESIGNER_RAG_TOP_K if assistant == "Workflow Designer" else RAG_TOP_K
    snippet_max = 220 if assistant == "Workflow Designer" else 300
    try:
        results = index.search(query, top_k=top_k, content_type=content_type)
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
        snippet = text.replace("\n", " ")[:snippet_max]
        if ct:
            entry = f"[{ct}] {label}: {snippet}"
        else:
            entry = f"{label}: {snippet}"
        if total + len(entry) + 2 > max_chars:
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
        from gui.flet.components.settings import get_rag_embedding_model, get_rag_index_dir, get_mydata_dir
        from rag.context_updater import need_indexing, run_update
    except ImportError:
        await show_toast(page, "RAG: update not available")
        return

    rag_index_data_dir = get_rag_index_dir()
    mydata_dir = get_mydata_dir()
    need_units, need_mydata, reason = await asyncio.to_thread(need_indexing, rag_index_data_dir, _UNITS_DIR, mydata_dir)
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
            rag_index_data_dir,
            _UNITS_DIR,
            mydata_dir,
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
