"""LoadDocument unit: Docling document → body_text + tables for doc_to_text workflow."""
from units.canonical.load_document.load_document import (
    LOAD_DOCUMENT_INPUT_PORTS,
    LOAD_DOCUMENT_OUTPUT_PORTS,
    register_load_document,
)

__all__ = ["register_load_document", "LOAD_DOCUMENT_INPUT_PORTS", "LOAD_DOCUMENT_OUTPUT_PORTS"]
