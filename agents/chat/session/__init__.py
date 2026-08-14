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
from .load_chat_history import (
    _history_dedupe_prefer_applied,  # pyright: ignore[reportPrivateUsage]
    load_chat_session,
)
from .session_management import (
    _sessions,  # pyright: ignore[reportPrivateUsage]
    _sessions_lock,  # pyright: ignore[reportPrivateUsage]
    create_session,
    get_session,
    remove_session,
    reset_session,
    stop_run,
)
from .state import (
    ChatSessionState,
    _Session,  # pyright: ignore[reportPrivateUsage]
    from_snapshot,
    get_typed,
    to_snapshot,
)

__all__ = [
    "ChatSessionState",
    "_Session",
    "_history_dedupe_prefer_applied",
    "_sessions",
    "_sessions_lock",
    "append_chat_message_delta",
    "build_chat_payload",
    "create_session",
    "from_snapshot",
    "get_session",
    "get_typed",
    "load_chat_session",
    "message_for_persist",
    "remove_session",
    "reset_session",
    "slugify_filename",
    "stop_run",
    "suggest_initial_chat_path",
    "to_snapshot",
    "unique_path",
    "write_chat_payload",
]
