"""RagDetectOrigin unit: detect graph origin via RAG discriminant; output origin + graph bypass."""
from units.canonical.rag_detect_origin.rag_detect_origin import (
    RAG_DETECT_ORIGIN_INPUT_PORTS,
    RAG_DETECT_ORIGIN_OUTPUT_PORTS,
    register_rag_detect_origin,
)

__all__ = [
    "register_rag_detect_origin",
    "RAG_DETECT_ORIGIN_INPUT_PORTS",
    "RAG_DETECT_ORIGIN_OUTPUT_PORTS",
]
