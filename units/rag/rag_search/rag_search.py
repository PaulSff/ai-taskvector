"""
RagSearch unit: RAG index search via Chroma + sentence-transformers.

Owns all search primitives (``query_semantic_raw``, ``_search_filtered``, path lookup).
Orchestration callers (``rag/search.py``, ``rag/indexer.py``) reach these via the
``rag_raw_search.json`` workflow — they do NOT import from this module directly.

Python API (``search()``, ``get_by_file_path()``) is re-exported via ``rag/__init__``
for the CLI (``from rag import search``).

Unit output ports: ``table`` (list of {text,metadata,score}), ``count`` (float),
``first`` (top result dict or None).

Params: persist_dir, embedding_model, top_k, content_type,
metadata_file_path_contains. Use ``settings.rag_index_data_dir`` and
``settings.rag_embedding_model`` in workflow JSON.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from units.canonical.app_settings_param import coerce_int_param
from units.registry import UnitSpec, register_unit

RAG_SEARCH_INPUT_PORTS = [("query", "str"), ("edits", "Any"), ("file_path", "str")]
RAG_SEARCH_OUTPUT_PORTS = [
    ("table", "Any"),  # list of {text, metadata, score}
    ("count", "float"),  # len(table)
    ("first", "Any"),  # table[0] or None
]


# ---------------------------------------------------------------------------
# Embedding model resolution
# ---------------------------------------------------------------------------


def _default_embedding_model() -> str:
    """Resolve default embedding model from app settings."""
    try:
        from gui.components.settings import get_rag_embedding_model

        return get_rag_embedding_model()
    except ImportError:
        return "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"


def _resolve_embedding_model(embedding_model: str | None) -> str:
    """Return the effective embedding model string (never empty)."""
    m = (embedding_model or "").strip()
    return m if m else _default_embedding_model()


def clear_rag_index_cache() -> None:
    """No-op stub kept for backward compatibility (called by RagUpdate and DeleteFromIndex)."""


# ---------------------------------------------------------------------------
# Low-level Chroma + embedder primitives
# ---------------------------------------------------------------------------


def _get_chroma_collection(persist_dir: str | Path) -> Any:
    """Open (or create) the RAG Chroma collection at ``persist_dir``."""
    from units.rag.chroma_indexer.chroma_indexer import get_rag_collection

    return get_rag_collection(persist_dir)


def _distance_to_score(d: float) -> float:
    """Convert cosine distance to similarity score (higher = better)."""
    try:
        x = float(d)
    except (TypeError, ValueError):
        return 0.0
    if x <= 1.0:
        return max(0.0, 1.0 - x)
    return 1.0 / (1.0 + x)


def query_semantic_raw(
    *,
    persist_dir: str | Path,
    embedding_model: str,
    query: str,
    top_k: int,
) -> list[dict[str, Any]]:
    """
    Low-level semantic search: embed ``query`` and return up to ``top_k`` hits as
    ``{text, metadata, score}`` sorted by descending score (best first).
    No content-type or file-path filtering — use ``search()`` for that.
    """
    from units.rag.embedder.embedder import encode_texts

    q = (query or "").strip()
    if not q:
        return []
    coll = _get_chroma_collection(persist_dir)
    qemb = encode_texts(embedding_model, [q])
    if not qemb:
        return []
    res = coll.query(
        query_embeddings=[qemb[0]],
        n_results=max(1, min(int(top_k), 500)),
        include=["documents", "metadatas", "distances"],
    )
    docs = (res.get("documents") or [[]])[0] or []
    metas = (res.get("metadatas") or [[]])[0] or []
    dists = (res.get("distances") or [[]])[0] or []
    rows: list[dict[str, Any]] = []
    for i, doc in enumerate(docs):
        d = dists[i] if i < len(dists) else 0.0
        meta = dict(metas[i]) if i < len(metas) and isinstance(metas[i], dict) else {}
        rows.append(
            {
                "text": doc if isinstance(doc, str) else str(doc),
                "metadata": meta,
                "score": _distance_to_score(d),
            }
        )
    rows.sort(key=lambda r: float(r.get("score") or 0.0), reverse=True)
    return rows


def _get_by_file_path_impl(
    file_path: str,
    *,
    persist_dir: str | Path,
) -> list[dict[str, Any]]:
    """
    Retrieve all chunks from the Chroma index whose ``metadata.file_path`` equals
    the given path. Tries resolved absolute path first, then verbatim. Score = 1.0.
    """
    path_str = (file_path or "").strip()
    if not path_str:
        return []
    result = None
    try:
        resolved = str(Path(path_str).resolve())
        coll = _get_chroma_collection(persist_dir)
        result = coll.get(
            where={"file_path": {"$eq": resolved}},
            include=["documents", "metadatas"],
        )
    except Exception:
        result = None
    if not result or not result.get("ids"):
        try:
            coll = _get_chroma_collection(persist_dir)
            result = coll.get(
                where={"file_path": {"$eq": path_str}},
                include=["documents", "metadatas"],
            )
        except Exception:
            result = None
    if not result or not result.get("ids"):
        return []
    docs = result.get("documents") or []
    metadatas = result.get("metadatas") or []
    out: list[dict[str, Any]] = []
    for i, meta in enumerate(metadatas):
        text = ""
        if i < len(docs):
            d = docs[i]
            text = (
                d[0]
                if isinstance(d, (list, tuple)) and d
                else (d if isinstance(d, str) else str(d))
            )
        out.append(
            {
                "text": text or "",
                "metadata": meta if isinstance(meta, dict) else {},
                "score": 1.0,
            }
        )
    return out


def _search_filtered(
    query: str,
    *,
    persist_dir: str | Path,
    embedding_model: str,
    top_k: int = 10,
    content_type: str | None = None,
    metadata_file_path_contains: str | None = None,
) -> list[dict[str, Any]]:
    """
    Semantic search with optional content-type and file-path-substring filters.
    Pulls extra candidates when filtering to ensure sufficient final hits.
    """
    needle = (metadata_file_path_contains or "").strip().replace("\\", "/") or None
    fetch_k = top_k * 2
    if needle:
        fetch_k = max(fetch_k, top_k * 25, 80)
    fetch_k = min(fetch_k, 500)
    rows = query_semantic_raw(
        persist_dir=persist_dir,
        embedding_model=embedding_model,
        query=query,
        top_k=fetch_k,
    )
    results: list[dict[str, Any]] = []
    for row in rows:
        meta = row.get("metadata") or {}
        if content_type and meta.get("content_type") != content_type:
            continue
        if needle:
            fp = str(meta.get("file_path") or "").replace("\\", "/")
            if needle not in fp:
                continue
        results.append(
            {
                "text": row.get("text") or "",
                "metadata": meta,
                "score": row.get("score"),
            }
        )
        if len(results) >= top_k:
            break
    return results


# ---------------------------------------------------------------------------
# Python API — used by CLI via ``from rag import search`` and rag/__init__
# ---------------------------------------------------------------------------


def search(
    query: str,
    *,
    persist_dir: str = ".rag_index",
    embedding_model: str | None = None,
    top_k: int = 10,
    content_type: str | None = None,
    metadata_file_path_contains: str | None = None,
) -> list[dict[str, Any]]:
    """
    Search the RAG index. Returns list of {text, metadata, score}.
    Direct implementation — no workflow overhead, suitable for CLI and Python callers.
    """
    emb = _resolve_embedding_model(embedding_model)
    return _search_filtered(
        query,
        persist_dir=persist_dir,
        embedding_model=emb,
        top_k=top_k,
        content_type=content_type,
        metadata_file_path_contains=metadata_file_path_contains,
    )


def get_by_file_path(
    file_path: str,
    *,
    persist_dir: str = ".rag_index",
    embedding_model: str | None = None,  # accepted but not needed for path lookup
) -> list[dict[str, Any]]:
    """
    Retrieve all indexed chunks for the given file path.
    Returns list of {text, metadata, score} (score 1.0 for exact path match).
    """
    return _get_by_file_path_impl(file_path, persist_dir=persist_dir)


# ---------------------------------------------------------------------------
# Edit-based search action helper
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Unit step function
# ---------------------------------------------------------------------------


def _rag_search_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run search: file_path input → path retrieval; else edits/query → filtered semantic search."""
    empty: dict[str, Any] = {"table": [], "count": 0.0, "first": None}
    if params.get("ignore"):
        return (empty, state)
    persist_dir = params.get("persist_dir")
    if persist_dir is None or not str(persist_dir).strip():
        return (empty, state)
    persist_dir = str(persist_dir).strip()

    embedding_model_raw = params.get("embedding_model")
    embedding_model = _resolve_embedding_model(
        str(embedding_model_raw).strip() if embedding_model_raw else None
    )

    # Path-based retrieval (read_file action)
    fp = inputs.get("file_path")
    if fp is not None and isinstance(fp, str) and fp.strip():
        try:
            results = _get_by_file_path_impl(fp.strip(), persist_dir=persist_dir)
        except Exception:
            results = []
        results = results if isinstance(results, list) else []
        return (
            {
                "table": results,
                "count": float(len(results)),
                "first": results[0] if results else None,
            },
            state,
        )

    # Semantic search: edits first, then query port
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
        return (empty, state)

    top_k_raw = (
        top_k_from_input if top_k_from_input is not None else params.get("top_k")
    )
    top_k = coerce_int_param(top_k_raw)
    content_type = params.get("content_type")
    mfpc = params.get("metadata_file_path_contains")
    if mfpc is not None:
        mfpc = str(mfpc).strip() or None

    try:
        results = _search_filtered(
            query,
            persist_dir=persist_dir,
            embedding_model=embedding_model,
            top_k=top_k if top_k is not None else 10,
            content_type=content_type,
            metadata_file_path_contains=mfpc,
        )
    except Exception:
        results = []

    results = results if isinstance(results, list) else []
    return (
        {
            "table": results,
            "count": float(len(results)),
            "first": results[0] if results else None,
        },
        state,
    )


# ---------------------------------------------------------------------------
# Unit registration
# ---------------------------------------------------------------------------


def register_rag_search() -> None:
    """Register the RagSearch unit type."""
    register_unit(
        UnitSpec(
            type_name="RagSearch",
            input_ports=RAG_SEARCH_INPUT_PORTS,
            output_ports=RAG_SEARCH_OUTPUT_PORTS,
            step_fn=_rag_search_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description=(
                "RAG index search: semantic (query or edits first action 'search') or "
                "path-based (file_path). "
                "Outputs: table (list of {text,metadata,score}), count (float), first (top result or None). "
                "Params: persist_dir, embedding_model, top_k, content_type, "
                "metadata_file_path_contains (path substring filter). "
                "Use settings.rag_index_data_dir / settings.rag_embedding_model in workflows."
            ),
        )
    )


__all__ = [
    "register_rag_search",
    "search",
    "get_by_file_path",
    "query_semantic_raw",
    "clear_rag_index_cache",
    "RAG_SEARCH_INPUT_PORTS",
    "RAG_SEARCH_OUTPUT_PORTS",
]
