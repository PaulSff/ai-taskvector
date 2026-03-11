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
WORKFLOW_DESIGNER_RAG_TOP_K = 5

# Min similarity score (0–1, higher = more similar) to include a result; only results that match the user message well are injected. None = no score filter.
RAG_MIN_SCORE = 0.48

# Repo root (gui/flet/chat_with_the_assistants -> 4 parents)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_UNITS_DIR = _REPO_ROOT / "units"

# Max chars returned for request_file_content (full file for assistant)
REQUEST_FILE_CONTENT_MAX_CHARS = 4000


def read_file_content_for_assistant(
    path_str: str,
    mydata_dir: Path,
    units_dir: Path,
    repo_root: Path,
    max_chars: int = REQUEST_FILE_CONTENT_MAX_CHARS,
) -> str | None:
    """
    Read file content for the assistant (request_file_content tool).
    Path must resolve under mydata_dir, units_dir, or repo_root. Returns None if invalid or unreadable.
    """
    path_str = (path_str or "").strip()
    if not path_str:
        return None
    try:
        p = Path(path_str)
        if not p.is_absolute():
            p = (repo_root / p).resolve()
        else:
            p = p.resolve()
        roots = [repo_root.resolve(), mydata_dir.resolve(), units_dir.resolve()]
        def _under_root(path: Path, root: Path) -> bool:
            try:
                path.resolve().relative_to(root.resolve())
                return True
            except ValueError:
                return False
        if not any(_under_root(p, r) for r in roots):
            return None
        if not p.is_file():
            return None
        text = p.read_text(encoding="utf-8", errors="replace")
        return text[:max_chars] if len(text) > max_chars else text
    except (OSError, ValueError):
        return None


def rag_query_from_graph_origin(graph: Any) -> str:
    """
    Build a RAG search query from the graph runtime (centralized detection).
    Used to retrieve relevant conventions/patterns when generating unit docs (augmenter).
    """
    from core.normalizer.runtime_detector import runtime_label

    rt = runtime_label(graph) if (hasattr(graph, "model_dump") or isinstance(graph, dict)) else "canonical"
    if rt == "canonical":
        return "workflow unit API documentation"
    if rt == "node_red":
        return "Node-RED node conventions patterns"
    if rt == "n8n":
        return "n8n node structure conventions"
    return "workflow node API documentation conventions"


def get_rag_context_via_workflow(query: str, assistant: str, top_k: int | None = None) -> str:
    """
    Retrieve RAG context by running the rag_context_workflow (rag_search -> rag_filter -> format_rag).
    Uses paths and RAG settings from app config. Returns formatted context string from FormatRagPrompt unit.
    """
    query = (query or "").strip()
    if not query:
        return ""
    try:
        from gui.flet.components.settings import (
            get_rag_context_workflow_path,
            get_rag_index_dir,
            get_rag_embedding_model,
        )
        from runtime.run import run_workflow
    except ImportError:
        return ""
    path = get_rag_context_workflow_path()
    if not path.exists():
        return ""
    top_k_val = top_k
    if top_k_val is None:
        top_k_val = WORKFLOW_DESIGNER_RAG_TOP_K if assistant == "Workflow Designer" else RAG_TOP_K
    top_k_val = max(1, min(50, int(top_k_val)))
    overrides = {
        "rag_search": {
            "persist_dir": str(get_rag_index_dir()),
            "embedding_model": get_rag_embedding_model(),
            "top_k": top_k_val,
        },
    }
    initial_inputs = {"rag_search": {"query": query}}
    try:
        outputs = run_workflow(
            path,
            initial_inputs=initial_inputs,
            unit_param_overrides=overrides,
        )
    except Exception:
        return ""
    return (outputs or {}).get("format_rag", {}).get("data") or ""


def get_rag_context(query: str, assistant: str, top_k: int | None = None) -> str:
    """
    Retrieve RAG context by running the rag_context_workflow (rag_search -> rag_filter -> format_rag).
    Uses paths and RAG settings from app config. No direct rag/ calls—workflow only.

    Args:
        query: User message (used as search query)
        assistant: "Workflow Designer" or "RL Coach"
        top_k: Optional max number of results. Clamped to 1–50.

    Returns:
        Formatted "Relevant context from the knowledge base: ..." block, or ""
    """
    return get_rag_context_via_workflow(query, assistant, top_k)


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
