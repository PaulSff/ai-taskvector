"""ChunkBuilder unit: Universal text chunking unit (chars/lines strategies)."""
from units.rag.chunk_builder.chunk_builder import (
    RAG_CHUNK_BUILDER_INPUT_PORTS,
    RAG_CHUNK_BUILDER_OUTPUT_PORTS,
    register_chunk_builder,
)

__all__ = [
    "register_chunk_builder",
    "RAG_CHUNK_BUILDER_INPUT_PORTS",
    "RAG_CHUNK_BUILDER_OUTPUT_PORTS",
]
