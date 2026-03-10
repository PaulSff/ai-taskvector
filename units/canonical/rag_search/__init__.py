"""RagSearch unit: query → RAG index results (table). Also exports search() for rag/ and CLI."""
from units.canonical.rag_search.rag_search import (
    RAG_SEARCH_INPUT_PORTS,
    RAG_SEARCH_OUTPUT_PORTS,
    register_rag_search,
    search,
)

__all__ = ["register_rag_search", "search", "RAG_SEARCH_INPUT_PORTS", "RAG_SEARCH_OUTPUT_PORTS"]
