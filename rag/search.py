"""
Search API for the RAG index.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def search(
    query: str,
    *,
    persist_dir: str = ".rag_index",
    embedding_model: str | None = None,
    top_k: int = 10,
    content_type: str | None = None,
) -> list[dict[str, Any]]:
    """
    Search the RAG index.

    Args:
        query: Natural language search query
        persist_dir: Path to the RAG index (default .rag_index)
        embedding_model: Override embedding model (default from settings or all-MiniLM-L6-v2)
        top_k: Max number of results
        content_type: Optional filter: "workflow", "node", or "document"

    Returns:
        List of {text, metadata, score}
    """
    from rag.indexer import RAGIndex

    index = RAGIndex(persist_dir=persist_dir, embedding_model=embedding_model)
    return index.search(query, top_k=top_k, content_type=content_type)
