"""
RAG-augmented context for assistants: retrieve relevant workflows, nodes, and documents
and inject them into the prompt for Workflow Designer and RL Coach.
Index update at startup runs via rag_update workflow (RagUpdate unit), not direct context_updater calls.
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

def rag_query_from_graph_origin(graph: Any) -> str:
    """
    Build a RAG search query from the graph runtime (centralized detection).
    Used to build RAG search queries from graph runtime (e.g. for workflow context).
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


def get_rag_context_via_workflow(
    query: str,
    assistant: str,
    top_k: int | None = None,
    max_chars: int | None = None,
    snippet_max: int | None = None,
) -> str:
    """
    Retrieve RAG context by running the rag_context_workflow (rag_search -> rag_filter -> format_rag).
    Uses paths and RAG settings from app config. Returns formatted context string from FormatRagPrompt unit.
    Optional max_chars (total block) and snippet_max (per-result snippet) override FormatRagPrompt params.
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
    overrides: dict[str, dict[str, Any]] = {
        "rag_search": {
            "persist_dir": str(get_rag_index_dir()),
            "embedding_model": get_rag_embedding_model(),
            "top_k": top_k_val,
        },
    }
    if max_chars is not None or snippet_max is not None:
        format_params: dict[str, int] = {}
        if max_chars is not None:
            format_params["max_chars"] = max(1, min(5000, int(max_chars)))
        if snippet_max is not None:
            format_params["snippet_max"] = max(1, min(2000, int(snippet_max)))
        if format_params:
            overrides["format_rag"] = format_params
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


# Default limits for read_file (path-based RAG retrieval): allow more content so the assistant can "read" the file
READ_FILE_VIA_RAG_MAX_CHARS = 8000
READ_FILE_VIA_RAG_SNIPPET_MAX = 4000


def get_rag_context_by_path(
    file_path: str,
    assistant: str,
    max_chars: int | None = None,
    snippet_max: int | None = None,
) -> str:
    """
    Retrieve file content from the RAG index by path (path-based retrieval).
    Runs rag_context_workflow with file_path set so RagSearch returns all chunks for that file;
    uses expanded max_chars/snippet_max so the assistant gets full indexed content.
    Returns formatted string or "" if the file is not in the index or workflow fails.
    """
    path_str = (file_path or "").strip()
    if not path_str:
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
    wf_path = get_rag_context_workflow_path()
    if not wf_path.exists():
        return ""
    mc = max_chars if max_chars is not None else READ_FILE_VIA_RAG_MAX_CHARS
    sm = snippet_max if snippet_max is not None else READ_FILE_VIA_RAG_SNIPPET_MAX
    mc = max(1, min(5000, int(mc)))
    sm = max(1, min(5000, int(sm)))  # allow larger snippets for read_file
    overrides: dict[str, dict[str, Any]] = {
        "rag_search": {
            "persist_dir": str(get_rag_index_dir()),
            "embedding_model": get_rag_embedding_model(),
        },
        "format_rag": {"max_chars": mc, "snippet_max": sm},
    }
    initial_inputs = {"rag_search": {"query": "", "file_path": path_str}}
    try:
        outputs = run_workflow(
            wf_path,
            initial_inputs=initial_inputs,
            unit_param_overrides=overrides,
        )
    except Exception:
        return ""
    return (outputs or {}).get("format_rag", {}).get("data") or ""


def get_rag_context(
    query: str,
    assistant: str,
    top_k: int | None = None,
    max_chars: int | None = None,
    snippet_max: int | None = None,
) -> str:
    """
    Retrieve RAG context by running the rag_context_workflow (rag_search -> rag_filter -> format_rag).
    Uses paths and RAG settings from app config. No direct rag/ calls—workflow only.

    Args:
        query: User message (used as search query)
        assistant: "Workflow Designer" or "RL Coach"
        top_k: Optional max number of results. Clamped to 1–50.
        max_chars: Optional total context length (1–5000). Overrides FormatRagPrompt max_chars.
        snippet_max: Optional chars per result snippet (1–2000). Overrides FormatRagPrompt snippet_max.

    Returns:
        Formatted "Relevant context from the knowledge base: ..." block, or ""
    """
    return get_rag_context_via_workflow(query, assistant, top_k, max_chars, snippet_max)


async def ensure_units_indexed_at_startup(page: ft.Page) -> None:
    """Run at GUI start: run rag_update workflow (RagUpdate unit), show spinner then toast with status."""
    from gui.flet.tools.notifications import show_toast

    try:
        from gui.flet.components.settings import (
            get_rag_update_workflow_path,
            get_rag_embedding_model,
            get_rag_index_dir,
            get_mydata_dir,
        )
        from runtime.run import run_workflow
    except ImportError:
        await show_toast(page, "RAG: update not available")
        return

    path = get_rag_update_workflow_path()
    if not path.exists():
        await show_toast(page, "RAG: rag_update workflow not found")
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

    overrides = {
        "rag_update": {
            "rag_index_data_dir": str(get_rag_index_dir()),
            "units_dir": str(_UNITS_DIR),
            "mydata_dir": str(get_mydata_dir()),
            "embedding_model": get_rag_embedding_model(),
        },
    }
    try:
        outputs = await asyncio.to_thread(
            run_workflow,
            path,
            initial_inputs=None,
            unit_param_overrides=overrides,
        )
        rag_out = (outputs or {}).get("rag_update") or {}
        result = rag_out.get("data") or {}
        error_port = rag_out.get("error")
    except Exception as e:
        result = {"error": str(e)[:200], "message": str(e)[:200]}
        error_port = None
    finally:
        if progress_overlay in page.overlay:
            page.overlay.remove(progress_overlay)
            page.update()

    if error_port and isinstance(error_port, str) and error_port.strip():
        await show_toast(page, f"RAG update error: {error_port[:150]}")
    elif result.get("error"):
        await show_toast(page, result["error"])
    else:
        await show_toast(page, result.get("message", result.get("details", "RAG: ok")))
