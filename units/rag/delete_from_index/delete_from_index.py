"""
**DeleteFromIndex** unit: remove RAG index chunks from ChromaDB by ``metadata.file_path``.

Input: ``file_paths`` (list of str — absolute or relative paths whose chunks should be deleted).
Output: ``count`` (float — total chunk IDs removed), ``error`` (str or None).
Params: ``persist_dir`` (required; use ``settings.rag_index_data_dir`` in workflows).

Each path is tried both as-is and resolved to an absolute path to match the form stored in the
index.  After deletion the **RagSearch** LRU cache is invalidated so the next search reflects the
updated index.

Use the ``rag/workflows/rag_delete_from_index.json`` workflow to invoke this unit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

DELETE_FROM_INDEX_INPUT_PORTS = [("file_paths", "Any")]
DELETE_FROM_INDEX_OUTPUT_PORTS = [("count", "float"), ("error", "str")]


def delete_chunks_by_file_paths(
    *,
    persist_dir: str | Path,
    file_paths: list[str],
) -> int:
    """
    Delete all Chroma chunks whose ``metadata.file_path`` matches any entry in ``file_paths``.
    Each path is tried both resolved (absolute) and verbatim so the caller does not need to know
    which form was stored at index time.
    Returns the total number of chunk IDs deleted.
    """
    from units.rag.chroma_indexer.chroma_indexer import get_rag_collection

    if not file_paths:
        return 0
    coll = get_rag_collection(persist_dir)
    ids_to_delete: list[str] = []
    seen: set[str] = set()
    for fp in file_paths:
        fp = (fp or "").strip()
        if not fp:
            continue
        candidates = [fp]
        try:
            resolved = str(Path(fp).resolve())
            if resolved != fp:
                candidates.append(resolved)
        except Exception:
            pass
        for path_str in candidates:
            try:
                result = coll.get(where={"file_path": {"$eq": path_str}}, include=[])
                for chunk_id in result.get("ids") or []:
                    if chunk_id not in seen:
                        seen.add(chunk_id)
                        ids_to_delete.append(chunk_id)
            except Exception:
                continue
    if ids_to_delete:
        coll.delete(ids=ids_to_delete)
    return len(ids_to_delete)


def _delete_from_index_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve file_paths from input, delete matching chunks, clear the search cache."""
    persist_dir = str(params.get("persist_dir") or "").strip()
    if not persist_dir:
        err = "persist_dir is required"
        return ({"count": 0.0, "error": err}, state)

    raw = inputs.get("file_paths")
    if raw is None:
        return ({"count": 0.0, "error": None}, state)
    if isinstance(raw, str):
        file_paths = [raw] if raw.strip() else []
    elif isinstance(raw, list):
        file_paths = [str(fp) for fp in raw if fp]
    else:
        file_paths = []

    if not file_paths:
        return ({"count": 0.0, "error": None}, state)

    try:
        n = delete_chunks_by_file_paths(persist_dir=persist_dir, file_paths=file_paths)
    except Exception as exc:
        err = str(exc)[:300]
        return ({"count": 0.0, "error": err}, state)

    # Invalidate the RagSearch LRU cache so subsequent searches reflect the deletion.
    try:
        from units.rag.rag_search.rag_search import clear_rag_index_cache

        clear_rag_index_cache()
    except Exception:
        pass

    return ({"count": float(n), "error": None}, state)


def register_delete_from_index() -> None:
    """Register the DeleteFromIndex unit type."""
    register_unit(
        UnitSpec(
            type_name="DeleteFromIndex",
            input_ports=DELETE_FROM_INDEX_INPUT_PORTS,
            output_ports=DELETE_FROM_INDEX_OUTPUT_PORTS,
            step_fn=_delete_from_index_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description=(
                "Delete RAG index chunks by file_path. "
                "Input: file_paths (list[str] or single str). "
                "Output: count (chunk IDs removed, float), error (str or None). "
                "Param: persist_dir (settings.rag_index_data_dir). "
                "Clears the RagSearch cache after deletion. "
                "Use rag/workflows/rag_delete_from_index.json."
            ),
        )
    )


__all__ = [
    "DELETE_FROM_INDEX_INPUT_PORTS",
    "DELETE_FROM_INDEX_OUTPUT_PORTS",
    "delete_chunks_by_file_paths",
    "register_delete_from_index",
]
