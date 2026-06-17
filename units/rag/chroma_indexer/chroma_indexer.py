"""
**ChromaIndexer** unit: ChromaDB **write** (embed + ``collection.add``) for the shared ``rag`` collection.

This unit only **indexes** chunks from parallel ``texts`` / ``metadatas`` inputs.
Semantic search lives in the **RagSearch** unit (``units/rag/rag_search``).
Deletion lives in the **DeleteFromIndex** unit (``units/rag/delete_from_index``).

Public helper used by other RAG units: ``get_rag_collection`` (returns the ChromaDB collection handle).
All other helpers (``_add_rag_chunks``, ``_rebuild_rag_collection``, ``_chroma_safe_metadata``) are
internal to this unit and not part of the public API.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from chromadb.config import Settings

from units.registry import UnitSpec, register_unit

# module-level cached process pool for indexer tasks
_INDEXER_POOL: Optional[ProcessPoolExecutor] = None


def _get_indexer_pool(max_workers: int = 1) -> ProcessPoolExecutor:
    global _INDEXER_POOL
    if _INDEXER_POOL is None:
        _INDEXER_POOL = ProcessPoolExecutor(max_workers=max_workers)
    return _INDEXER_POOL


RAG_COLLECTION_NAME = "rag"
_ADD_BATCH = 64

_CLIENT_LOCK = Lock()
_CLIENT_CACHE: dict[str, Any] = {}

CHROMA_INDEXER_INPUT_PORTS = [
    ("texts", "Any"),
    ("metadatas", "Any"),
    ("embeddings", "Any"),
]
CHROMA_INDEXER_OUTPUT_PORTS = [("count", "float")]


def _get_background_loop_from_params(
    params: dict[str, Any],
) -> asyncio.AbstractEventLoop | None:
    bg = params.get("_background_loop") or params.get("_executor_loop")
    if isinstance(bg, asyncio.AbstractEventLoop):
        return bg
    exec_obj = params.get("_executor")
    if exec_obj is not None:
        bg = getattr(exec_obj, "background_loop", None) or getattr(
            exec_obj, "loop", None
        )
        if isinstance(bg, asyncio.AbstractEventLoop):
            return bg
    return None


def _schedule_on_background_loop(
    coro: Any, background_loop: asyncio.AbstractEventLoop
) -> Any:
    if (
        not isinstance(background_loop, asyncio.AbstractEventLoop)
        or not background_loop.is_running()
    ):
        raise RuntimeError("background loop not running")
    fut = asyncio.run_coroutine_threadsafe(coro, background_loop)
    return fut.result()


def _chroma_safe_metadata(meta: dict[str, Any]) -> dict[str, Any]:
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


def _get_chroma_client(
    persist_dir: str | Path, anonymized_telemetry: bool = False
) -> Any:
    """
    Return a cached ``chromadb.PersistentClient`` for ``persist_dir``.
    One client per resolved path and telemetry setting is kept alive for the process lifetime.
    """
    import chromadb  # type: ignore[import-untyped]

    root = str(Path(persist_dir).expanduser().resolve())
    cache_key = f"{root}|telemetry={anonymized_telemetry}"
    cached = _CLIENT_CACHE.get(
        cache_key
    )  # fast path — no lock needed for dict read under CPython GIL
    if cached is not None:
        return cached
    with _CLIENT_LOCK:
        if cache_key not in _CLIENT_CACHE:
            Path(root).mkdir(parents=True, exist_ok=True)
            settings = Settings(anonymized_telemetry=anonymized_telemetry)
            # persistent client stored under chroma_db directory
            _CLIENT_CACHE[cache_key] = chromadb.PersistentClient(
                path=str(Path(root) / "chroma_db"), settings=settings
            )
        return _CLIENT_CACHE[cache_key]


def get_rag_collection(persist_dir: str | Path) -> Any:
    """Return the ``rag`` ChromaDB collection at ``persist_dir`` (client is cached)."""
    return _get_chroma_client(persist_dir).get_or_create_collection(
        RAG_COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )


def _chunk_id(global_index: int, file_path: str, text: str) -> str:
    h = hashlib.sha256(
        f"{global_index}\0{file_path}\0{text[:800]}".encode("utf-8", errors="replace"),
    ).hexdigest()
    return f"rag_{h}"


def _add_rag_chunks(
    *,
    persist_dir: str | Path,
    embedding_model: str,
    chunks: list[tuple[str, dict[str, Any]]],
    precomputed_embeddings: list[list[float]] | None = None,
    anonymized_telemetry: bool = False,
) -> int:
    """
    Internal: embed and upsert ``(text, metadata)`` chunk pairs into the Chroma collection.
    Uses pre-computed embeddings when provided and length-matched; otherwise calls ``encode_texts``.
    """
    if not chunks:
        return 0
    from units.rag.embedder.embedder import encode_texts

    # create/get client with telemetry option, then get/create the collection
    client = _get_chroma_client(persist_dir, anonymized_telemetry)
    coll = client.get_or_create_collection(
        RAG_COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )

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
        metas = [_chroma_safe_metadata(m) for _, m in slice_]
        ids = [
            _chunk_id(global_i + j, str(m.get("file_path") or ""), texts[j])
            for j, (_, m) in enumerate(slice_)
        ]
        global_i += len(slice_)
        if use_pre:
            assert (
                precomputed_embeddings is not None
            )  # narrowed: use_pre is True only when not None
            embeddings = precomputed_embeddings[start : start + len(texts)]
        else:
            embeddings = encode_texts(embedding_model, texts)
        coll.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metas)
        total += len(slice_)
    return total


def _rebuild_rag_collection(
    *,
    persist_dir: str | Path,
    embedding_model: str,
    chunks: list[tuple[str, dict[str, Any]]],
    anonymized_telemetry: bool = False,
) -> int:
    """Internal: drop the ``rag`` collection then rebuild it from ``chunks``."""
    client = _get_chroma_client(persist_dir, anonymized_telemetry=anonymized_telemetry)
    try:
        client.delete_collection(RAG_COLLECTION_NAME)
    except Exception:
        pass
    # _add_rag_chunks → get_rag_collection → get_or_create_collection recreates the collection.
    return _add_rag_chunks(
        persist_dir=persist_dir, embedding_model=embedding_model, chunks=chunks
    )


def _chroma_indexer_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    persist_dir = str(params.get("persist_dir") or "").strip()
    model = str(params.get("embedding_model") or "").strip()
    anonymized_telemetry = bool(params.get("anonymized_telemetry", False))
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

    # Early return if there is nothing to index or precomputed embeddings don't match
    if not (
        isinstance(pre, list)
        and pairs
        and len(pre) == len(pairs)
        and all(isinstance(x, list) for x in pre)
    ):
        return {"count": 0.0}, state

    pre_list = pre  # type: ignore[assignment]

    # Prepare the callable for indexing work (same args as original synchronous call)
    func = functools.partial(
        _add_rag_chunks,
        persist_dir=persist_dir,
        embedding_model=model,
        chunks=pairs,
        precomputed_embeddings=pre_list,
        anonymized_telemetry=anonymized_telemetry,
    )

    background_loop = _get_background_loop_from_params(params)
    if (
        isinstance(background_loop, asyncio.AbstractEventLoop)
        and background_loop.is_running()
    ):
        try:
            coro = background_loop.run_in_executor(_get_indexer_pool(), func)
            result = _schedule_on_background_loop(coro, background_loop)
        except Exception:
            # fallback to original synchronous behavior on any error
            result = _add_rag_chunks(
                persist_dir=persist_dir,
                embedding_model=model,
                chunks=pairs,
                precomputed_embeddings=pre_list,
                anonymized_telemetry=anonymized_telemetry,
            )
    else:
        # no background loop provided — preserve original synchronous behavior
        result = _add_rag_chunks(
            persist_dir=persist_dir,
            embedding_model=model,
            chunks=pairs,
            precomputed_embeddings=pre_list,
            anonymized_telemetry=anonymized_telemetry,
        )

    n = float(result)
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
    "get_rag_collection",
    "register_chroma_indexer",
]
