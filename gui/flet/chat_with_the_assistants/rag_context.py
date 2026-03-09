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


def get_rag_context(query: str, assistant: str, top_k: int | None = None) -> str:
    """
    Retrieve relevant context from the RAG index for the given assistant.
    Returns formatted string to inject into the prompt, or empty string if unavailable.

    Only results with similarity score >= RAG_MIN_SCORE are included, so the injected context
    matches the user's message.

    Args:
        query: User message (used as search query)
        assistant: "Workflow Designer" or "RL Coach"
        top_k: Optional max number of results (e.g. from search action max_results). Clamped to 1–50.

    Returns:
        Formatted "Relevant context from the knowledge base: ..." block, or ""
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
    max_chars = WORKFLOW_DESIGNER_RAG_MAX_CHARS if assistant == "Workflow Designer" else RAG_CONTEXT_MAX_CHARS
    default_top_k = WORKFLOW_DESIGNER_RAG_TOP_K if assistant == "Workflow Designer" else RAG_TOP_K
    if top_k is not None:
        top_k = max(1, min(50, int(top_k)))
    else:
        top_k = default_top_k
    # Snippet length: long enough so mid-doc sections (e.g. "RLOracle" in PIPELINES-WIRING.md) can appear when relevant
    snippet_max = 400 if assistant == "Workflow Designer" else 300
    try:
        results = index.search(query, top_k=top_k, content_type=content_type)
    except Exception:
        return ""

    if not results:
        return ""

    # Collect (content_type, entry) respecting score and max_chars per entry
    typed: list[tuple[str, str]] = []
    total = 0
    for r in results:
        if RAG_MIN_SCORE is not None:
            score = r.get("score")
            if score is not None and score < RAG_MIN_SCORE:
                continue
        meta = r.get("metadata") or {}
        text = (r.get("text") or "").strip()
        if not text:
            continue
        ct = meta.get("content_type", "") or "other"
        source = meta.get("file_path") or meta.get("raw_json_path") or meta.get("source") or meta.get("id") or "?"
        label = meta.get("name") or source
        snippet = text.replace("\n", " ")[:snippet_max]
        if ct and ct != "other":
            entry = f"[{ct}] {label}: {snippet}"
        else:
            entry = f"{label}: {snippet}"
        if total + len(entry) + 2 > max_chars:
            break
        typed.append((ct, entry))
        total += len(entry) + 2

    if not typed:
        return ""

    # Group by content_type and add visual separators (Documents / Workflows / Other)
    section_sep = "\n\n--- "
    section_end = " ---\n\n"
    order = ("document", "workflow", "flow_library", "node", "other")
    by_type: dict[str, list[str]] = {}
    for ct, entry in typed:
        key = ct if ct in order else "other"
        by_type.setdefault(key, []).append(entry)
    block_parts = ["Relevant context from knowledge base:"]
    section_labels = {"document": "Documents", "workflow": "Workflows", "flow_library": "Flow libraries", "node": "Nodes", "other": "Other"}
    for key in order:
        if key not in by_type:
            continue
        label = section_labels.get(key, key.replace("_", " ").capitalize() + "s")
        block_parts.append(section_sep + label + section_end + "\n\n".join(by_type[key]))
    block = "".join(block_parts)
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
