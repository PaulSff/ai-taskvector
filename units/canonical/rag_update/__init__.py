"""RagUpdate unit: run RAG index update from workflow (rag.context_updater.run_update)."""
from units.canonical.rag_update.rag_update import (
    RAG_UPDATE_INPUT_PORTS,
    RAG_UPDATE_OUTPUT_PORTS,
    register_rag_update,
)

__all__ = ["register_rag_update", "RAG_UPDATE_INPUT_PORTS", "RAG_UPDATE_OUTPUT_PORTS"]
