"""
RAG retrieval: Chroma collection access, semantic search, and path/id lookups.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def get_chroma_collection(persist_dir: str | Path) -> Any:
    """Return the underlying ChromaDB collection for metadata queries and search."""
    from units.rag.chroma_indexer.chroma_indexer import get_rag_collection

    return get_rag_collection(persist_dir)


def get_node_by_id(index: Any, node_id: str) -> dict[str, Any] | None:
    """
    Look up a node (catalogue entry) by id from the RAG index.
    Returns metadata dict or None if not found.
    """
    try:
        coll = get_chroma_collection(index.persist_dir)
        result = coll.get(
            where={"$and": [{"content_type": {"$eq": "node"}}, {"id": {"$eq": str(node_id)}}]},
            include=["metadatas"],
        )
        if result and result.get("metadatas") and len(result["metadatas"]) > 0:
            return dict(result["metadatas"][0])
    except Exception:
        pass
    return None


def get_by_file_path(index: Any, file_path: str) -> list[dict[str, Any]]:
    """
    Retrieve all chunks from the index whose metadata file_path equals the given path.
    Used for read_file action: get full indexed content for a file by path.
    Returns list of {text, metadata, score} (score is 1.0 for path-based retrieval).
    Path is normalized to absolute for matching (index stores absolute paths).
    """
    path_str = (file_path or "").strip()
    if not path_str:
        return []
    result = None
    try:
        resolved = str(Path(path_str).resolve())
        coll = get_chroma_collection(index.persist_dir)
        result = coll.get(
            where={"file_path": {"$eq": resolved}},
            include=["documents", "metadatas"],
        )
    except Exception:
        result = None
    if (not result or not result.get("ids")):
        try:
            coll = get_chroma_collection(index.persist_dir)
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
    # Chroma may return documents as list of lists for multi-embedding; take first element if so
    out: list[dict[str, Any]] = []
    for i, meta in enumerate(metadatas):
        text = ""
        if i < len(docs):
            d = docs[i]
            text = d[0] if isinstance(d, (list, tuple)) and d else (d if isinstance(d, str) else str(d))
        out.append({
            "text": text or "",
            "metadata": meta if isinstance(meta, dict) else {},
            "score": 1.0,
        })
    return out


def search_index(
    index: Any,
    query: str,
    top_k: int = 10,
    content_type: str | None = None,
    metadata_file_path_contains: str | None = None,
) -> list[dict]:
    """
    Search the index. Returns list of {text, metadata, score}.
    content_type: optional filter on ``metadata.content_type`` (e.g. ``workflow``, ``node``,
    ``document``, ``taskvector_units_source``, ``unit_readme``, ``taskvector_units_readme``,
    ``role_source``, ``role_readme``, ``tool_source``, ``tool_readme``,
    ``taskvector_<folder>_readme`` / ``taskvector_<folder>_source``, …).
    metadata_file_path_contains: optional substring matched against metadata ``file_path``
    (after normalizing ``\\`` to ``/``). When set, only matching chunks are returned; the
    retriever pulls extra candidates so similarity-ranked hits are still found (e.g. team
    member RAG doc vs. the rest of the index).
    """
    from units.rag.chroma_indexer.chroma_indexer import query_semantic_raw

    needle = (metadata_file_path_contains or "").strip().replace("\\", "/") or None
    fetch_k = top_k * 2
    if needle:
        fetch_k = max(fetch_k, top_k * 25, 80)
    fetch_k = min(fetch_k, 500)
    rows = query_semantic_raw(
        persist_dir=str(index.persist_dir),
        embedding_model=index.embedding_model,
        query=query,
        top_k=fetch_k,
    )
    results: list[dict] = []
    for row in rows:
        meta = row.get("metadata") or {}
        if content_type and meta.get("content_type") != content_type:
            continue
        if needle:
            fp = str(meta.get("file_path") or "").replace("\\", "/")
            if needle not in fp:
                continue
        results.append({
            "text": row.get("text") or "",
            "metadata": meta,
            "score": row.get("score"),
        })
        if len(results) >= top_k:
            break
    return results
