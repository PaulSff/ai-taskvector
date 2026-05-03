"""PlainTextExtract unit: read a plain-text file and produce one RAG {text, metadata} item."""

from units.rag.plain_text_extract.plain_text_extract import (
    PLAIN_TEXT_EXTRACT_INPUT_PORTS,
    PLAIN_TEXT_EXTRACT_OUTPUT_PORTS,
    register_plain_text_extract,
)

__all__ = [
    "register_plain_text_extract",
    "PLAIN_TEXT_EXTRACT_INPUT_PORTS",
    "PLAIN_TEXT_EXTRACT_OUTPUT_PORTS",
]
