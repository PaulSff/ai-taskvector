from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


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


# Session data structure (minimal)
class _Session:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = _now_ts()
        self.history: List[Dict[str, Any]] = []
        self.busy = False
        self.has_sent_any = False
        self.chat_path: Optional[Path] = None
        self.session_language: str = ""
        self.last_apply_result: Optional[Dict[str, Any]] = None
        # run control
        self.run_token = 0
        self.run_lock = threading.Lock()
        # streaming buffer & flags
        self.stream_buffer = ""
        self.stream_rich = False
        self.thread_result: Any = None
        self.applied_flag = True


def to_snapshot(s: _Session) -> dict:
    """Return a serializable snapshot (compatible with ChatSessionState/persistence)."""
    # Acquire run_lock to get a consistent view of shared fields
    with s.run_lock:
        return {
            "session_id": s.session_id,
            "created_at": s.created_at,
            "history": list(s.history),
            "busy": bool(s.busy),
            "has_sent_any": bool(s.has_sent_any),
            "chat_path": str(s.chat_path) if s.chat_path is not None else None,
            "session_language": s.session_language,
            "last_apply_result": s.last_apply_result,
            # Do not include runtime-only fields: run_lock, stream_buffer, thread_result, applied_flag
        }


def from_snapshot(payload: Mapping[str, Any]) -> _Session:
    """Create a new _Session and populate serializable fields from payload."""
    sid = payload.get("session_id") or str(uuid.uuid4())
    s = _Session(sid)
    # populate simple fields (no locking needed for fresh object)
    s.created_at = payload.get("created_at", s.created_at)
    hist = payload.get("history")
    if isinstance(hist, list):
        s.history = list(hist)
    s.busy = bool(payload.get("busy", s.busy))
    s.has_sent_any = bool(payload.get("has_sent_any", s.has_sent_any))
    chat_path = payload.get("chat_path")
    if isinstance(chat_path, str) and chat_path:
        try:
            s.chat_path = Path(chat_path)
        except Exception:
            s.chat_path = None
    s.session_language = payload.get("session_language", s.session_language)
    s.last_apply_result = payload.get("last_apply_result", None)
    # leave runtime-only fields at defaults (fresh run_token, locks, buffers)
    return s
