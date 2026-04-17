"""ChatHistoryExtract unit: structure-aware chat history extractor with optional char chunking; outputs grouped or chunked text + metadata."""
from units.rag.chat_history_extractor.chat_history_extractor import (
    CHAT_HISTORY_EXTRACT_INPUT_PORTS,
    CHAT_HISTORY_EXTRACT_OUTPUT_PORTS,
    register_chat_history_extract,
)

__all__ = [
    "register_chat_history_extract",
    "CHAT_HISTORY_EXTRACT_INPUT_PORTS",
    "CHAT_HISTORY_EXTRACT_OUTPUT_PORTS",
]
