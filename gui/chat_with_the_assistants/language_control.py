"""
Session language for Workflow Designer chat: /lang commands, merge hints, and pinning from workflow output.

Pinning uses ``response["language"]`` from assistant_workflow runs. Call
``maybe_pin_session_language_from_workflow_response`` after every workflow response
so same-turn follow-ups and post-apply see ``state.session_language`` in injects.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Protocol


from assistants.roles.workflow_designer.workflow_inputs import default_wf_language_hint


class _SessionLanguageSink(Protocol):
    session_language: str


def parse_session_language_command(text: str) -> str | None:
    """
    If text is a session-language command, return the new value for ``ChatSessionState.session_language``.

    - ``/lang …`` or ``/language …`` (non-empty tail) sets session_language to that string.
    - ``/lang reset``, ``/lang clear``, ``/lang default`` (case-insensitive) clears session_language.

    Returns None if the message is not such a command (e.g. normal chat).
    """
    s = text.strip()
    m = re.match(r"^/(?:language|lang)\s+(.+)$", s, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    rest = (m.group(1) or "").strip()
    if not rest:
        return None
    low = rest.lower()
    if low in ("reset", "clear", "default"):
        return ""
    return rest


def maybe_pin_session_language_from_workflow_response(
    state: _SessionLanguageSink,
    response: dict[str, Any] | None,
) -> bool:
    """
    If ``response`` includes a non-empty ``language`` field and the session has no
    pinned language yet, set ``state.session_language`` and return True.
    """
    if not response or str(state.session_language or "").strip():
        return False
    detected = str(response.get("language") or "").strip()
    if not detected:
        return False
    state.session_language = detected
    return True


def finalize_workflow_designer_turn_session_language(
    state: _SessionLanguageSink,
    response: dict[str, Any] | None,
    *,
    debug_log: Callable[[str], None] | None = None,
) -> None:
    """
    End-of-turn: pin from the final ``response`` if still unset (safety net), then
    optional debug line matching previous chat.py behavior.
    """
    detected = str((response or {}).get("language") or "").strip()
    if detected and not str(state.session_language or "").strip():
        state.session_language = detected
        if debug_log:
            debug_log(f"session_language pinned to {state.session_language!r}")
    elif debug_log:
        debug_log(
            "session_language unchanged "
            f"(pinned={state.session_language!r}, detected={detected!r})"
        )
