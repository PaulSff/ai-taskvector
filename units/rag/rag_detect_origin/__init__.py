"""RagDetectOrigin unit: detect graph content_kind for json via rag.content_types.registry; output origin + graph bypass."""

from units.rag.rag_detect_origin.rag_detect_origin import (
    RAG_DETECT_ORIGIN_INPUT_PORTS,
    RAG_DETECT_ORIGIN_OUTPUT_PORTS,
    register_rag_detect_origin,
)

__all__ = [
    "register_rag_detect_origin",
    "RAG_DETECT_ORIGIN_INPUT_PORTS",
    "RAG_DETECT_ORIGIN_OUTPUT_PORTS",
]
