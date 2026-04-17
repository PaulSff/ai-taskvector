"""RagCanonicalWorkflowExtract unit: self-contained canonical workflow extractor aligned with extractors.py canonical behavior."""
from units.rag.rag_canonical_workflow_extractor.rag_canonical_workflow_extractor import (
    RAG_CANONICAL_WORKFLOW_EXTRACT_INPUT_PORTS,
    RAG_CANONICAL_WORKFLOW_EXTRACT_OUTPUT_PORTS,
    register_rag_canonical_workflow_extract,
)

__all__ = [
    "register_rag_canonical_workflow_extract",
    "RAG_CANONICAL_WORKFLOW_EXTRACT_INPUT_PORTS",
    "RAG_CANONICAL_WORKFLOW_EXTRACT_OUTPUT_PORTS",
]
