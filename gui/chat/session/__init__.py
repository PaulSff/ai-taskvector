"""Chat session state and persistence (history files, payload I/O)."""

from .chat_persistence import (
    build_chat_payload,
    message_for_persist,
    suggest_initial_chat_path,
)
from .history_store import (
    append_chat_message_delta,
    slugify_filename,
    unique_path,
    write_chat_payload,
)
from .load_chat_history import load_chat_session, _history_dedupe_prefer_applied
from .session_management import (
    _sessions,
    _sessions_lock,
    create_session,
    get_session,
    remove_session,
    reset_session,
    stop_run,
)
from .state import ChatSessionState, _Session, from_snapshot, to_snapshot

__all__ = [
    "create_session",
    "reset_session",
    "ChatSessionState",
    "_Session",
    "from_snapshot",
    "to_snapshot",
    "load_chat_session",
    "write_chat_payload",
    "append_chat_message_delta",
    "slugify_filename",
    "unique_path",
    "build_chat_payload",
    "message_for_persist",
    "suggest_initial_chat_path",
    "_sessions",
    "_sessions_lock",
    "stop_run",
    "get_session",
    "remove_session",
    "_history_dedupe_prefer_applied",
]
