"""
**ChromaIndexer** unit: ChromaDB **write** (embed + ``collection.add``) for the shared ``rag`` collection.

Semantic **search** belongs in **RagSearch** (``rag/search.py`` → ``query_semantic_raw`` with filters
and caching). This unit only **indexes** chunks from parallel ``texts`` / ``metadatas`` inputs.

Python helpers (used by ``rag/indexer.py`` / ``rag/search.py`` and this unit):
  - ``chroma_safe_metadata``, ``get_rag_collection``, ``add_rag_chunks``, ``rebuild_rag_collection``
  - ``query_semantic_raw`` — used only by ``rag/search.search_index`` (not exposed as unit behavior)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

RAG_COLLECTION_NAME = "rag"
_ADD_BATCH = 64

CHROMA_INDEXER_INPUT_PORTS = [("texts", "Any"), ("metadatas", "Any"), ("embeddings", "Any")]
CHROMA_INDEXER_OUTPUT_PORTS = [("count", "float")]


def chroma_safe_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Chroma allows str, int, float, bool, None. Serialize list/dict to JSON string."""
    out: dict[str, Any] = {}
    for k, v in meta.items():
        if v is None or isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, (list, dict)):
            out[k] = json.dumps(v, ensure_ascii=False) if v else ""
        else:
            out[k] = str(v)
    return out


def get_rag_collection(persist_dir: str | Path) -> Any:
    import chromadb

    root = Path(persist_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    db = chromadb.PersistentClient(path=str(root / "chroma_db"))
    return db.get_or_create_collection(RAG_COLLECTION_NAME, metadata={"hnsw:space": "cosine"})


def _chunk_id(global_index: int, file_path: str, text: str) -> str:
    h = hashlib.sha256(
        f"{global_index}\0{file_path}\0{text[:800]}".encode("utf-8", errors="replace"),
    ).hexdigest()
    return f"rag_{h}"


def add_rag_chunks(
    *,
    persist_dir: str | Path,
    embedding_model: str,
    chunks: list[tuple[str, dict[str, Any]]],
    precomputed_embeddings: list[list[float]] | None = None,
) -> int:
    """
    ``chunks`` are ``(text, metadata)`` pairs. Embeds with the Embedder stack and ``collection.add``s in batches,
    unless ``precomputed_embeddings`` is set and has the same length as ``chunks`` (one vector per chunk).
    """
    if not chunks:
        return 0
    from units.rag.embedder.embedder import encode_texts

    coll = get_rag_collection(persist_dir)
    total = 0
    global_i = 0
    n = len(chunks)
    use_pre = (
        precomputed_embeddings is not None
        and len(precomputed_embeddings) == n
        and all(isinstance(row, list) and row for row in precomputed_embeddings)
    )
    for start in range(0, len(chunks), _ADD_BATCH):
        slice_ = chunks[start : start + _ADD_BATCH]
        texts = [t for t, _ in slice_]
        metas = [chroma_safe_metadata(m) for _, m in slice_]
        ids = [_chunk_id(global_i + j, str(m.get("file_path") or ""), texts[j]) for j, (_, m) in enumerate(slice_)]
        global_i += len(slice_)
        if use_pre:
            embeddings = precomputed_embeddings[start : start + len(texts)]
        else:
            embeddings = encode_texts(embedding_model, texts)
        coll.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metas)
        total += len(slice_)
    return total


def rebuild_rag_collection(
    *,
    persist_dir: str | Path,
    embedding_model: str,
    chunks: list[tuple[str, dict[str, Any]]],
) -> int:
    """Drop the ``rag`` collection and rebuild from ``chunks`` (full index build / fallback)."""
    import chromadb

    root = Path(persist_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    db = chromadb.PersistentClient(path=str(root / "chroma_db"))
    try:
        db.delete_collection(RAG_COLLECTION_NAME)
    except Exception:
        pass
    db.get_or_create_collection(RAG_COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    return add_rag_chunks(persist_dir=persist_dir, embedding_model=embedding_model, chunks=chunks)


def _distance_to_score(d: float) -> float:
    """Higher is better for ranking (cosine space: distance often 1 - similarity for normalized vectors)."""
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
    Return up to ``top_k`` hits as ``{text, metadata, score}`` sorted by descending score (best first).
    """
    from units.rag.embedder.embedder import encode_texts

    q = (query or "").strip()
    if not q:
        return []
    coll = get_rag_collection(persist_dir)
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
        rows.append({
            "text": doc if isinstance(doc, str) else str(doc),
            "metadata": meta,
            "score": _distance_to_score(d),
        })
    rows.sort(key=lambda r: float(r.get("score") or 0.0), reverse=True)
    return rows


def _chroma_indexer_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    persist_dir = str(params.get("persist_dir") or "").strip()
    model = str(params.get("embedding_model") or "").strip()
    if not persist_dir or not model:
        return {"count": 0.0}, state
    texts_raw = inputs.get("texts")
    metas_raw = inputs.get("metadatas")
    texts = texts_raw if isinstance(texts_raw, list) else []
    metas = metas_raw if isinstance(metas_raw, list) else []
    pairs: list[tuple[str, dict[str, Any]]] = []
    for i, t in enumerate(texts):
        m = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
        s = str(t).strip()
        if s:
            pairs.append((s, m))
    pre = inputs.get("embeddings")
    pre_list: list[list[float]] | None = None
    if (
        isinstance(pre, list)
        and pairs
        and len(pre) == len(pairs)
        and all(isinstance(x, list) for x in pre)
    ):
        pre_list = pre  # type: ignore[assignment]
    n = float(
        add_rag_chunks(
            persist_dir=persist_dir,
            embedding_model=model,
            chunks=pairs,
            precomputed_embeddings=pre_list,
        ),
    )
    return {"count": n}, state


def register_chroma_indexer() -> None:
    register_unit(
        UnitSpec(
            type_name="ChromaIndexer",
            input_ports=CHROMA_INDEXER_INPUT_PORTS,
            output_ports=CHROMA_INDEXER_OUTPUT_PORTS,
            step_fn=_chroma_indexer_step,
            role="rag_index",
            description="ChromaDB chunk upsert: inputs texts + metadatas → output count. Use RagSearch for semantic retrieval.",
        )
    )


__all__ = [
    "CHROMA_INDEXER_INPUT_PORTS",
    "CHROMA_INDEXER_OUTPUT_PORTS",
    "add_rag_chunks",
    "chroma_safe_metadata",
    "get_rag_collection",
    "query_semantic_raw",
    "rebuild_rag_collection",
    "register_chroma_indexer",
]
