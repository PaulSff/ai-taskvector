import threading
import uuid
from typing import Dict, Optional

from .state import _Session

_sessions: Dict[str, _Session] = {}
_sessions_lock = threading.Lock()


def create_session(session_id: Optional[str] = None) -> str:
    """Create or return an existing session id."""
    sid = session_id or str(uuid.uuid4())
    with _sessions_lock:
        if sid not in _sessions:
            _sessions[sid] = _Session(sid)
    return sid


def reset_session(session_id: str) -> None:
    """Reset session state and remove persisted chat_path reference (does not delete files)."""
    with _sessions_lock:
        s = _sessions.get(session_id)
        if s is None:
            return
        s.history.clear()
        s.busy = False
        s.has_sent_any = False
        s.chat_path = None
        s.session_language = ""
        s.last_apply_result = None
        s.run_token = 0
        s.stream_buffer = ""
        s.stream_rich = False
        s.thread_result = None
        s.applied_flag = True
