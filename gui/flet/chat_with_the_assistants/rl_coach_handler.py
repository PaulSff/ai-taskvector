"""
RL Coach assistant handler: message building for chat.

RL Coach does not apply config edits in Flet yet; it streams and appends the raw response.
"""
from __future__ import annotations

from typing import Any, Callable


def build_rl_coach_messages(
    history: list[dict[str, Any]],
    user_message: str,
    messages_from_history: Callable[..., list[dict[str, str]]],
    *,
    system_prompt: str,
    rag_context: str | None = None,
) -> list[dict[str, str]]:
    """Build LLM messages: system + history + user (with optional RAG context)."""
    msgs: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    msgs.extend(messages_from_history(history))
    user_content = user_message
    if rag_context:
        user_content = f"{rag_context}\n\nUser request: {user_message}"
    msgs.append({"role": "user", "content": user_content})
    return msgs
