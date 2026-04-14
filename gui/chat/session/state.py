from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ChatSessionState:
    """Mutable session state for a single chat session."""

    history: list[dict[str, Any]]
    busy: bool
    has_sent_any: bool

    session_id: str
    created_at: str
    chat_path: Path | None
    session_language: str

