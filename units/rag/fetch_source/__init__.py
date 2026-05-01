"""FetchSource unit: unified local/remote source resolver for RAG ingestion."""

from units.rag.fetch_source.fetch_source import (
    FETCH_SOURCE_INPUT_PORTS,
    FETCH_SOURCE_OUTPUT_PORTS,
    register_fetch_source,
)

__all__ = [
    "register_fetch_source",
    "FETCH_SOURCE_INPUT_PORTS",
    "FETCH_SOURCE_OUTPUT_PORTS",
]
