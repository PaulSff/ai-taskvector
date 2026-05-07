"""
RAG search orchestration: run rag_raw_search.json via the workflow executor.

This is the orchestration-layer entry point used by ``rag/indexer.py`` and any
other Python callers that want to search the index without importing from units
directly.  The workflow approach keeps all search logic inside the
``RagSearch`` unit (``units/rag/rag_search/rag_search.py``).

For direct Python access (CLI, ``from rag import search``) the unit's own
``search()`` / ``get_by_file_path()`` are re-exported via ``rag/__init__``
— those call Chroma + the embedder directly with no workflow overhead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _raw_search_wf_path() -> Path:
    """Absolute path to rag_raw_search.json (path resolved from ragconf)."""
    from rag.ragconf_loader import rag_raw_search_workflow_path_raw

    return Path(__file__).resolve().parent.parent / rag_raw_search_workflow_path_raw()


def _run_search_workflow(
    *,
    initial_inputs: dict[str, Any],
    persist_dir: str | Path,
    embedding_model: str | None = None,
    top_k: int | None = None,
    content_type: str | None = None,
    metadata_file_path_contains: str | None = None,
    timeout_s: float = 30.0,
) -> list[dict[str, Any]]:
    """Execute rag_raw_search.json and return the ``rag_search`` unit's ``table`` output."""
    from runtime.run import run_workflow

    wf_path = _raw_search_wf_path()
    if not wf_path.is_file():
        return []

    param_overrides: dict[str, Any] = {"persist_dir": str(persist_dir)}
    if embedding_model:
        param_overrides["embedding_model"] = str(embedding_model)
    if top_k is not None:
        param_overrides["top_k"] = int(top_k)
    if content_type:
        param_overrides["content_type"] = str(content_type)
    if metadata_file_path_contains:
        param_overrides["metadata_file_path_contains"] = str(
            metadata_file_path_contains
        )

    try:
        outputs = run_workflow(
            wf_path,
            initial_inputs=initial_inputs,
            unit_param_overrides={"rag_search": param_overrides},
            execution_timeout_s=timeout_s,
        )
    except Exception:
        return []

    result = (outputs or {}).get("rag_search", {})
    table = result.get("table") if isinstance(result, dict) else None
    return table if isinstance(table, list) else []


def search(
    query: str,
    *,
    persist_dir: str | Path = ".rag_index",
    embedding_model: str | None = None,
    top_k: int = 10,
    content_type: str | None = None,
    metadata_file_path_contains: str | None = None,
) -> list[dict[str, Any]]:
    """
    Search the RAG index via workflow. Returns list of {text, metadata, score}.
    Runs rag_raw_search.json wiring inject_query -> RagSearch.query.
    """
    return _run_search_workflow(
        initial_inputs={"inject_query": {"data": query}},
        persist_dir=persist_dir,
        embedding_model=embedding_model,
        top_k=top_k,
        content_type=content_type,
        metadata_file_path_contains=metadata_file_path_contains,
    )


def get_by_file_path(
    file_path: str,
    *,
    persist_dir: str | Path = ".rag_index",
    embedding_model: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve all indexed chunks for the given file path via workflow.
    Runs rag_raw_search.json wiring inject_file_path -> RagSearch.file_path.
    """
    return _run_search_workflow(
        initial_inputs={"inject_file_path": {"data": file_path}},
        persist_dir=persist_dir,
        embedding_model=embedding_model,
    )
