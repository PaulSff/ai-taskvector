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

from assistants.roles import WORKFLOW_DESIGNER_ROLE_ID, get_role

# RAG limits: assistants/tools/rag_search/tool.yaml, roles/*/role.yaml, tools/read_file/tool.yaml (see settings getters).

# Repo root (gui/chat -> 3 parents)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_UNITS_DIR = _REPO_ROOT / "units"


def _assistant_uses_workflow_designer_rag_top_k(assistant: str | None) -> bool:
    """True when RAG should use Workflow Designer–specific top_k (role id or display_name from registry)."""
    a = (assistant or "").strip()
    if not a:
        return True
    if a == WORKFLOW_DESIGNER_ROLE_ID:
        return True
    try:
        return a == get_role(WORKFLOW_DESIGNER_ROLE_ID).display_name
    except Exception:
        return False

def rag_query_from_graph_origin(graph: Any) -> str:
    """
    Build a RAG search query from the graph runtime (via RuntimeLabel workflow).
    Used to build RAG search queries from graph runtime (e.g. for workflow context).
    """
    from gui.components.workflow_tab.workflows.core_workflows import run_runtime_label

    rt, _ = run_runtime_label(graph) if (hasattr(graph, "model_dump") or isinstance(graph, dict)) else ("canonical", True)
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
    Retrieve RAG context by running the RAG context workflow (rag_search -> rag_filter -> format_rag).
    Uses paths and RAG settings from app config. Returns formatted context string from FormatRagPrompt unit.
    Workflow binds RAG caps via ``tool.rag_search.rag.*``; optional call-time ``max_chars`` /
    ``snippet_max`` override ``format_rag`` with integer literals.
    """
    query = (query or "").strip()
    if not query:
        return ""
    try:
        from gui.components.settings import (
            get_rag_context_workflow_path,
            get_rag_format_max_chars,
            get_rag_format_snippet_max,
            get_rag_top_k,
            get_workflow_designer_rag_top_k,
        )
        from runtime.run import run_workflow
    except ImportError:
        return ""
    path = get_rag_context_workflow_path()
    if not path.exists():
        return ""
    top_k_val = top_k
    if top_k_val is None:
        top_k_val = (
            get_workflow_designer_rag_top_k()
            if _assistant_uses_workflow_designer_rag_top_k(assistant)
            else get_rag_top_k()
        )
    top_k_val = max(1, min(50, int(top_k_val)))
    overrides: dict[str, dict[str, Any]] = {"rag_search": {"top_k": top_k_val}}
    if max_chars is not None or snippet_max is not None:
        fc = get_rag_format_max_chars()
        fs = get_rag_format_snippet_max()
        if max_chars is not None:
            fc = max(1, min(5000, int(max_chars)))
        if snippet_max is not None:
            fs = max(1, min(2000, int(snippet_max)))
        overrides["format_rag"] = {"max_chars": fc, "snippet_max": fs}
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


def get_rag_context_by_path(
    file_path: str,
    assistant: str,
    max_chars: int | None = None,
    snippet_max: int | None = None,
    *,
    rag_format_tool: str = "read_file",
) -> str:
    """
    Retrieve file content from the RAG index by path (path-based retrieval).
    Runs the RAG context workflow (path from ``assistants/tools/rag_search/tool.yaml`` via get_rag_context_workflow_path) with file_path set so RagSearch returns all chunks for that file;
    Overrides ``format_rag`` to ``tool.<rag_format_tool>.rag.*`` (e.g. ``read_file``, ``read_code_block``) unless ``max_chars`` / ``snippet_max``
    are passed, then those ports use the given integer literals.
    Returns formatted string or "" if the file is not in the index or workflow fails.
    """
    path_str = (file_path or "").strip()
    if not path_str:
        return ""
    tool_id = (rag_format_tool or "read_file").strip() or "read_file"
    try:
        from gui.components.settings import get_rag_context_workflow_path
        from runtime.run import run_workflow
        from units.canonical.app_settings_param import resolve_param_ref
    except ImportError:
        return ""
    wf_path = get_rag_context_workflow_path()
    if not wf_path.exists():
        return ""
    overrides: dict[str, dict[str, Any]] = {
        "rag_filter": {"value": "tool.rag_search.rag.min_score"},
        "format_rag": {
            "max_chars": f"tool.{tool_id}.rag.max_chars",
            "snippet_max": f"tool.{tool_id}.rag.snippet_max",
        },
    }
    if max_chars is not None or snippet_max is not None:
        fc_key = f"tool.{tool_id}.rag.max_chars"
        fs_key = f"tool.{tool_id}.rag.snippet_max"
        fc = int(max_chars) if max_chars is not None else int(resolve_param_ref(fc_key) or 8000)
        fs = int(snippet_max) if snippet_max is not None else int(resolve_param_ref(fs_key) or 4000)
        overrides["format_rag"] = {"max_chars": max(1, fc), "snippet_max": max(1, fs)}
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
    Retrieve RAG context by running the RAG context workflow (rag_search -> rag_filter -> format_rag).
    Uses paths and RAG settings from app config. No direct rag/ calls—workflow only.

    Args:
        query: User message (used as search query)
        assistant: role id (e.g. ``workflow_designer``) or that role's ``display_name`` from registry
        top_k: Optional max number of results. Clamped to 1–50.
        max_chars: Optional total context length (1–5000). Overrides FormatRagPrompt max_chars.
        snippet_max: Optional chars per result snippet (1–2000). Overrides FormatRagPrompt snippet_max.

    Returns:
        Formatted "Relevant context from the knowledge base: ..." block, or ""
    """
    return get_rag_context_via_workflow(query, assistant, top_k, max_chars, snippet_max)


async def ensure_units_indexed_at_startup(page: ft.Page) -> None:
    """Run at GUI start: run rag_update workflow (RagUpdate unit), show spinner then toast with status."""
    from gui.utils.notifications import show_toast

    try:
        from gui.components.settings import (
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
