from __future__ import annotations

import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, TypeVar, cast, final

from gui.utils import _now_ts


@dataclass
class ChatSessionState:
    """Mutable session state for a single chat session."""
    history: list[dict[str, object]]
    busy: bool
    has_sent_any: bool
    session_id: str
    created_at: str
    chat_path: Path | None
    session_language: str

class SessionSnapshot(TypedDict):
    """Strictly typed structure for session snapshots to avoid 'object' casting."""
    session_id: str
    created_at: str
    history: list[dict[str, object]]
    busy: bool
    has_sent_any: bool
    chat_path: str | None
    session_language: str
    messenger: str | None
    last_apply_result: dict[str, object] | None

@final
class _Session:
    def __init__(self, session_id: str):
        self.session_id: str = session_id
        self.created_at: str = _now_ts()
        self.history: list[dict[str, object]] = []
        self.busy: bool = False
        self.has_sent_any: bool = False
        self.chat_path: Path | None = None
        self.session_language: str = ""
        self.messenger: str | None = None
        self.last_apply_result: dict[str, object] | None = None
        # run control
        self.run_token: int = 0
        self.run_lock: threading.Lock = threading.Lock()
        # streaming buffer & flags
        self.stream_buffer: str = ""
        self.stream_rich: bool = False
        self.thread_result: object | None = None
        self.applied_flag: bool = True

def to_snapshot(s: _Session) -> SessionSnapshot:
    """Return a serializable snapshot. Returns a TypedDict to ensure type safety downstream."""
    with s.run_lock:
        return {
            "session_id": s.session_id,
            "created_at": s.created_at,
            "history": list(s.history),
            "busy": bool(s.busy),
            "has_sent_any": bool(s.has_sent_any),
            "chat_path": str(s.chat_path) if s.chat_path is not None else None,
            "session_language": s.session_language,
            "messenger": s.messenger,
            "last_apply_result": s.last_apply_result,
        }

T = TypeVar("T")

def get_typed[T](payload: Mapping[str, object], key: str, default: T, expected_type: type[T]) -> T:
    """
    Gets a value from the payload. If it exists and matches expected_type, returns it.
    Otherwise, returns the default value.
    """
    value = payload.get(key)
    if isinstance(value, expected_type):
        return value
    return default

def from_snapshot(payload: Mapping[str, object]) -> _Session:
    """Create a new _Session and populate serializable fields from payload."""
    # 1. Session ID
    sid = str(payload.get("session_id") or uuid.uuid4())
    s = _Session(sid)

    # 2. Simple Fields
    s.created_at = get_typed(payload, "created_at", s.created_at, str)
    s.busy = get_typed(payload, "busy", s.busy, bool)
    s.has_sent_any = get_typed(payload, "has_sent_any", s.has_sent_any, bool)
    s.session_language = get_typed(payload, "session_language", s.session_language, str)
    s.messenger = get_typed(payload, "messenger", None, str) # type: ignore

    # 3. History
    hist = payload.get("history")
    if isinstance(hist, list):
        s.history = [
            cast(dict[str, object], item)
            for item in cast(list[object], hist)
            if isinstance(item, dict)
        ]

    # 4. Chat Path
    chat_path_raw = payload.get("chat_path")
    if isinstance(chat_path_raw, str) and chat_path_raw:
        try:
            s.chat_path = Path(chat_path_raw)
        except (TypeError, ValueError):
            s.chat_path = None

    # 5. Last Apply Result
    last_res = payload.get("last_apply_result")
    if isinstance(last_res, dict):
        s.last_apply_result = cast(dict[str, object], last_res)
    else:
        s.last_apply_result = None

    return s
