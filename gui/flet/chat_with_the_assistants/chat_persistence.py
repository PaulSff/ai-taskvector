"""
Chat history persistence: payload building, sanitization, and file creation.

Used by the assistants chat panel for auto-save and load. Actual read/write
is delegated to history_store.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from gui.flet.chat_with_the_assistants.history_store import unique_path, write_chat_payload


def sanitize_config(cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Strip secret-like keys from config for persistence."""
    safe: dict[str, Any] = {}
    for k, v in (cfg or {}).items():
        ks = str(k).lower()
        if any(s in ks for s in ("key", "token", "secret", "password")):
            continue
        safe[str(k)] = v
    return safe


# UI-only keys on in-memory message dicts (not JSON-serializable).
_SKIP_MESSAGE_PERSIST_KEYS = frozenset({"_flet_row"})


def _message_for_persist(m: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in m.items() if k not in _SKIP_MESSAGE_PERSIST_KEYS}


def message_for_persist(m: dict[str, Any]) -> dict[str, Any]:
    """Public wrapper for persisting a single message dict."""
    return _message_for_persist(m)


def build_chat_payload(
    *,
    schema_version: int,
    session_id: str,
    created_at: str,
    assistant_selected: str | None,
    session_language: str | None,
    chat_history_dir: Path,
    messages: list[dict[str, Any]],
    get_llm_provider: Callable[[str], str],
    get_llm_provider_config: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    """Build the payload dict for persisting chat to disk."""
    wd_provider = get_llm_provider("workflow_designer")
    wd_cfg = get_llm_provider_config("workflow_designer")
    rl_provider = get_llm_provider("rl_coach")
    rl_cfg = get_llm_provider_config("rl_coach")

    return {
        "schema_version": schema_version,
        "session_id": session_id,
        "created_at": created_at,
        "assistant_selected": assistant_selected,
        "session_language": str(session_language or ""),
        "llm_profiles": {
            "workflow_designer": {"provider": wd_provider, "config": sanitize_config(wd_cfg)},
            "rl_coach": {"provider": rl_provider, "config": sanitize_config(rl_cfg)},
        },
        "chat_history_dir": str(chat_history_dir),
        "messages": [_message_for_persist(dict(x)) for x in messages if isinstance(x, dict)],
    }


def suggest_initial_chat_path(chat_history_dir: Path) -> Path:
    """Return a unique path for a new chat (timestamped)."""
    ts = datetime.now().strftime("%y-%m-%d-%H%M%S")
    return unique_path(chat_history_dir, f"chat_{ts}")
