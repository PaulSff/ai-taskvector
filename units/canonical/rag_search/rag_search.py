"""
RagSearch unit: RAG index search. Self-contained (no rag/search.py).

Input: query (str); optional edits (list of action dicts). When edits is connected and contains
an action "search", the first such action is used: what/query/q → query, max_results → top_k.
Params: persist_dir, embedding_model, top_k, content_type.
Output: table (list of {text, metadata, score}) for wiring to data_bi Filter or other consumers.

Also exposes search() for CLI and rag/__init__.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

RAG_SEARCH_INPUT_PORTS = [("query", "str"), ("edits", "Any")]
RAG_SEARCH_OUTPUT_PORTS = [("table", "Any")]  # list of {text, metadata, score}


def _search_action_from_edits(edits: Any) -> tuple[str, int | None] | None:
    """Return (query, top_k) from first edit with action=='search', or None."""
    if not isinstance(edits, list):
        return None
    for e in edits:
        if not isinstance(e, dict) or e.get("action") != "search":
            continue
        q = (e.get("what") or e.get("query") or e.get("q")) or ""
        if isinstance(q, str):
            q = q.strip()
        if not q:
            continue
        top_k = e.get("max_results")
        if top_k is not None:
            try:
                top_k = max(1, min(50, int(top_k)))
            except (TypeError, ValueError):
                top_k = None
        return (q, top_k)
    return None


def search(
    query: str,
    *,
    persist_dir: str = ".rag_index",
    embedding_model: str | None = None,
    top_k: int = 10,
    content_type: str | None = None,
) -> list[dict[str, Any]]:
    """
    Search the RAG index. Returns list of {text, metadata, score}.
    Used by the RagSearch unit and by rag CLI / from rag import search.
    """
    from rag.indexer import RAGIndex

    index = RAGIndex(persist_dir=persist_dir, embedding_model=embedding_model)
    return index.search(query, top_k=top_k, content_type=content_type)


def _rag_search_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run RAG index search; use edits (first search action) when provided, else query input. When ignore=True, skip search and return empty table (e.g. follow-up run where RAG context is injected separately)."""
    if params.get("ignore"):
        return ({"table": []}, state)
    query = ""
    top_k_from_input: int | None = None
    from_edits = _search_action_from_edits(inputs.get("edits"))
    if from_edits is not None:
        query, top_k_from_input = from_edits
    if not query:
        q = inputs.get("query")
        if q is None:
            q = ""
        if isinstance(q, dict):
            q = q.get("content", q.get("text", "")) or ""
        query = str(q).strip()
    if not query:
        return ({"table": []}, state)

    persist_dir = params.get("persist_dir")
    if persist_dir is None or not str(persist_dir).strip():
        return ({"table": []}, state)
    persist_dir = str(persist_dir).strip()
    embedding_model = params.get("embedding_model")
    top_k = top_k_from_input if top_k_from_input is not None else params.get("top_k")
    content_type = params.get("content_type")
    if top_k is not None:
        try:
            top_k = int(top_k)
        except (TypeError, ValueError):
            top_k = None

    try:
        results = search(
            query,
            persist_dir=persist_dir,
            embedding_model=embedding_model,
            top_k=top_k if top_k is not None else 10,
            content_type=content_type,
        )
    except Exception:
        results = []

    if not isinstance(results, list):
        results = []
    return ({"table": results}, state)


def register_rag_search() -> None:
    """Register the RagSearch unit type."""
    register_unit(UnitSpec(
        type_name="RagSearch",
        input_ports=RAG_SEARCH_INPUT_PORTS,
        output_ports=RAG_SEARCH_OUTPUT_PORTS,
        step_fn=_rag_search_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="RAG index search: query or edits (first action 'search') → table. Params: persist_dir, embedding_model, top_k, content_type. Wire query from user message or edits from parser.",
    ))


__all__ = ["register_rag_search", "search", "RAG_SEARCH_INPUT_PORTS", "RAG_SEARCH_OUTPUT_PORTS"]
