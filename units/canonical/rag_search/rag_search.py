"""
RagSearch unit: RAG index search. Self-contained (no rag/search.py).

Input: query (str); optional edits (list of action dicts); optional file_path (str). When file_path
is set, retrieves all chunks for that path from the index (path-based retrieval for read_file).
Otherwise when edits contains action "search", the first such action is used: what/query/q → query,
max_results → top_k. Params: persist_dir, embedding_model, top_k, content_type. Use ``settings.rag_index_data_dir`` and
``settings.rag_embedding_model`` in workflow JSON (resolved by the executor via ``app_settings_param``).
Output: table (list of {text, metadata, score}) for wiring to data_bi Filter or other consumers.

Also exposes search() for CLI and rag/__init__.
"""
from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

from units.canonical.app_settings_param import coerce_int_param
from units.registry import UnitSpec, register_unit

RAG_SEARCH_INPUT_PORTS = [("query", "str"), ("edits", "Any"), ("file_path", "str")]
RAG_SEARCH_OUTPUT_PORTS = [("table", "Any")]  # list of {text, metadata, score}

# Reuse loaded index/model wrappers across calls for chat latency.
# Keyed by effective RAG runtime settings that affect index/model handles.
_RAG_INDEX_CACHE: dict[tuple[str, str, bool], Any] = {}
_RAG_INDEX_CACHE_LOCK = Lock()

def _effective_embedding_model(embedding_model: str | None) -> str:
    """Resolve embedding model to a stable cache-key string."""
    model = (embedding_model or "").strip()
    if model:
        return model
    try:
        from rag.indexer import _default_rag_embedding_model
        return (_default_rag_embedding_model() or "").strip()
    except Exception:
        return ""


def _effective_rag_offline() -> bool:
    """Read RAG offline setting for cache-key segregation (``rag/ragconf.yaml``)."""
    try:
        from rag.ragconf_loader import rag_offline_raw

        return bool(rag_offline_raw())
    except Exception:
        return False


def _cache_key(persist_dir: str, embedding_model: str | None) -> tuple[str, str, bool]:
    """Cache key for RAG index instances."""
    p = str(Path(persist_dir).expanduser().resolve())
    return (p, _effective_embedding_model(embedding_model), _effective_rag_offline())


def clear_rag_index_cache() -> None:
    """Clear cached RAGIndex handles (call after index updates or settings changes)."""
    with _RAG_INDEX_CACHE_LOCK:
        _RAG_INDEX_CACHE.clear()


def _get_cached_index(
    *,
    persist_dir: str,
    embedding_model: str | None,
) -> Any:
    """Get/create cached RAGIndex for this persist_dir/model/offline tuple."""
    from rag.indexer import RAGIndex

    key = _cache_key(persist_dir, embedding_model)
    with _RAG_INDEX_CACHE_LOCK:
        idx = _RAG_INDEX_CACHE.get(key)
        if idx is not None:
            return idx
        idx = RAGIndex(persist_dir=persist_dir, embedding_model=embedding_model)
        _RAG_INDEX_CACHE[key] = idx
        return idx


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
    index = _get_cached_index(persist_dir=persist_dir, embedding_model=embedding_model)
    return index.search(query, top_k=top_k, content_type=content_type)


def get_by_file_path(
    file_path: str,
    *,
    persist_dir: str = ".rag_index",
    embedding_model: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve all indexed chunks for the given file path. Returns list of {text, metadata, score}.
    Used by the RagSearch unit when file_path input is set (read_file action).
    """
    index = _get_cached_index(persist_dir=persist_dir, embedding_model=embedding_model)
    return index.get_by_file_path(file_path)


def _rag_search_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run RAG index search; when file_path is set do path-based retrieval; else use edits (first search action) or query. When ignore=True, skip and return empty table."""
    if params.get("ignore"):
        return ({"table": []}, state)
    persist_dir = params.get("persist_dir")
    if persist_dir is None or not str(persist_dir).strip():
        return ({"table": []}, state)
    persist_dir = str(persist_dir).strip()
    embedding_model = params.get("embedding_model")
    if not persist_dir:
        return ({"table": []}, state)

    # Path-based retrieval (read_file): get all chunks for this file from the index
    fp = inputs.get("file_path")
    if fp is not None and isinstance(fp, str) and fp.strip():
        try:
            results = get_by_file_path(
                fp.strip(),
                persist_dir=persist_dir,
                embedding_model=embedding_model,
            )
        except Exception:
            results = []
        return ({"table": results if isinstance(results, list) else []}, state)

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

    top_k_raw = top_k_from_input if top_k_from_input is not None else params.get("top_k")
    top_k = coerce_int_param(top_k_raw)
    content_type = params.get("content_type")

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
        description="RAG index search: query or edits (first action 'search') → table. Params: persist_dir, embedding_model, top_k, content_type (use settings.rag_index_data_dir / settings.rag_embedding_model in workflows). Wire query from user message or edits from parser.",
    ))


__all__ = [
    "register_rag_search",
    "search",
    "get_by_file_path",
    "clear_rag_index_cache",
    "RAG_SEARCH_INPUT_PORTS",
    "RAG_SEARCH_OUTPUT_PORTS",
]
