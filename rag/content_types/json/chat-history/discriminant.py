"""Chat-history JSON: ``messages`` list of ``{role, content}`` or top-level list of the same."""

from __future__ import annotations

from pathlib import Path
from typing import Any

CONTENT_KIND = "chat_history"
PRIORITY = 0


def _is_message_dict(d: Any) -> bool:
    return isinstance(d, dict) and "role" in d and "content" in d


def matches(path: Path, data: dict | list) -> bool:
    del path  # reserved for path-based rules
    if isinstance(data, dict):
        messages = data.get("messages")
        return isinstance(messages, list) and all(_is_message_dict(m) for m in messages)
    if isinstance(data, list):
        return bool(data) and all(_is_message_dict(m) for m in data)
    return False
