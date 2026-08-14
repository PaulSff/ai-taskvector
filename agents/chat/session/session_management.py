import threading
import uuid

from .state import _Session  # pyright: ignore[reportPrivateUsage]

# Global session registry
_sessions: dict[str, _Session] = {}
_sessions_lock = threading.Lock()


def create_session(session_id: str | None = None) -> str:
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
        s.messenger = None
        s.last_apply_result = None
        s.run_token = 0
        s.stream_buffer = ""
        s.stream_rich = False
        s.thread_result = None
        s.applied_flag = True


def stop_run(session_id: str) -> None:
    """Signal stopping the currently active run by advancing the run token."""
    with _sessions_lock:
        s = _sessions.get(session_id)
        if s is None:
            return
        with s.run_lock:
            s.run_token += 1


def get_session(session_id: str) -> _Session | None:
    """Return the runtime _Session for session_id, or None if not found."""
    with _sessions_lock:
        return _sessions.get(session_id)


def remove_session(session_id: str) -> None:
    """Remove a session from the registry if present."""
    with _sessions_lock:
        _ = _sessions.pop(session_id, None)
