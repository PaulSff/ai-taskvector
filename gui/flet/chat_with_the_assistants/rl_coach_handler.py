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
) -> list[dict[str, str]]:
    """Build LLM messages: system + history + user."""
    msgs: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    msgs.extend(messages_from_history(history))
    msgs.append({"role": "user", "content": user_message})
    return msgs
