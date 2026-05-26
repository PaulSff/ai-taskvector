"""
Ollama integration wrapper.

This module centralizes interaction with the local/remote Ollama server so UIs (Flet, CLI)
don't depend directly on ollama-python details.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

OLLAMA_DEFAULT_HOST = "http://127.0.0.1:11434"
OLLAMA_DEFAULT_TIMEOUT_S = 300


def format_ollama_exception(e: Exception) -> str:
    """Human-friendly error string for common Ollama failures."""
    msg = str(e).strip()
    low = msg.lower()
    if any(
        s in low
        for s in [
            "connection refused",
            "failed to connect",
            "cannot connect",
            "connection error",
        ]
    ):
        return (
            "Couldn't connect to Ollama. Make sure the Ollama app/service is running and the host/port are correct. "
            "Quick check: run `ollama list` in a terminal."
        )
    if "vocab only" in low or "skipping tensors" in low:
        return (
            "Ollama loaded only the vocabulary and skipped tensors — the model files may be corrupt/incomplete. "
            "Try: `ollama rm <model>` then `ollama pull <model>`."
        )
    if "timeout" in low or "timed out" in low:
        return (
            "Request timed out. Ollama may be loading the model (first request can take 1–2 minutes on CPU). "
            "Try again or use a smaller model."
        )
    if "500" in low or "internal server error" in low:
        return (
            "Ollama returned 500. This can happen if the prompt is too large or the model fails to load. "
            "Try a smaller model and consider re-pulling it."
        )
    return f"Ollama error: {msg}"


# Provider-agnostic alias (used by LLM_integrations.client)
def format_exception(e: Exception) -> str:
    return format_ollama_exception(e)


def _extract_content_piece(response: Any) -> str:
    """Get message content from Ollama response (dict or object). Always return a string (no stripping)."""
    try:
        msg = (
            response.get("message", {})
            if isinstance(response, dict)
            else getattr(response, "message", None)
        )
        if msg is None:
            return ""
        if isinstance(msg, dict):
            content = msg.get("content") or msg.get("thinking") or ""
        else:
            content = (
                getattr(msg, "content", None) or getattr(msg, "thinking", None) or ""
            )
        return (content or "") if content is not None else ""
    except Exception:
        return ""


def _extract_content(response: Any) -> str:
    """Get message content from Ollama response (dict or object). Always return a string."""
    return _extract_content_piece(response).strip()


def _ollama_client_kwargs(
    host: str, timeout_s: int, api_key: str | None
) -> dict[str, Any]:
    """Build kwargs for ollama Client (host, timeout, optional Authorization header for Cloud)."""
    kwargs: dict[str, Any] = {"host": host, "timeout": timeout_s}
    if (api_key or "").strip():
        kwargs["headers"] = {"Authorization": f"Bearer {(api_key or '').strip()}"}
    return kwargs


# --- Cloud detection helper ---


def _is_cloud_model(model: str) -> bool:
    """
    Detect Ollama Cloud model names.

    Heuristic:
    - Lowercase model string.
    - Treat as cloud if it ends with ":cloud" or "-cloud" or the last token after ':' ends with "cloud".
    Examples: "qwen3-coder:480b-cloud", "qwen3-coder-next:cloud", "gpt:cloud"
    """
    m = (model or "").strip().lower()
    if not m:
        return False
    if m.endswith(":cloud") or m.endswith("-cloud"):
        return True
    parts = m.split(":")
    if parts and parts[-1].endswith("cloud"):
        return True
    return False


# --- Structured -> raw prompt conversion for offline/unstructured models ---


def _messages_to_raw_prompt(messages: list[dict[str, str]]) -> str:
    """
    Convert structured messages (role/content) into a single raw prompt string.

    Format (deterministic):
    ### System
    <system content>

    ### User
    <user content>

    ### Assistant
    <assistant content>
    ...
    """
    parts: list[str] = []
    for m in messages:
        role = (m.get("role") or "user").strip().lower()
        content = m.get("content") or ""
        label = role.title()
        parts.append(f"### {label}\n{content}")
    return "\n\n".join(parts)


def _call_client_chat_with_messages(
    client, model: str, messages: list[dict[str, str]], options: dict[str, Any]
) -> Any:
    """
    Call client.chat according to model type.

    Strict behavior: use structured messages only for cloud models (per _is_cloud_model).
    For non-cloud models always convert messages to a single raw user prompt and call client.chat
    with that single message. No runtime fallback or signature probing is performed.
    """
    if _is_cloud_model(model):
        return client.chat(model=model, messages=messages, options=options or {})

    # Non-cloud/offline models: convert to a single raw prompt (unstructured)
    raw = _messages_to_raw_prompt(messages)
    fallback_messages = [{"role": "user", "content": raw}]
    return client.chat(model=model, messages=fallback_messages, options=options or {})


def chat(
    *,
    host: str = OLLAMA_DEFAULT_HOST,
    model: str,
    messages: list[dict[str, str]],
    timeout_s: int = OLLAMA_DEFAULT_TIMEOUT_S,
    options: dict[str, Any] | None = None,
    api_key: str | None = None,
) -> str:
    """
    Call Ollama chat and return assistant content.

    Requires `pip install ollama` and an Ollama server at host (local or Cloud).
    For Ollama Cloud, set api_key (or OLLAMA_API_KEY env) and use a cloud model name (e.g. qwen3-coder:480b-cloud).
    """
    try:
        from ollama import Client  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "Ollama is not installed. Install with: pip install ollama"
        ) from e

    kwargs = _ollama_client_kwargs(host, timeout_s, api_key)
    client = Client(**kwargs)
    resp = _call_client_chat_with_messages(
        client, model=model, messages=messages, options=options or {}
    )
    return _extract_content(resp)


def chat_stream(
    *,
    host: str = OLLAMA_DEFAULT_HOST,
    model: str,
    messages: list[dict[str, str]],
    timeout_s: int = OLLAMA_DEFAULT_TIMEOUT_S,
    options: dict[str, Any] | None = None,
    api_key: str | None = None,
) -> Iterator[str]:
    """
    Stream Ollama chat and yield assistant content pieces (partial tokens).

    Notes:
    - This yields incremental pieces; caller should concatenate.
    - Requires `pip install ollama`.
    - For Cloud, pass api_key (or set OLLAMA_API_KEY env).
    - Mode selection is strict based on model name only.
      - Cloud models: use structured streaming call (stream=True). No runtime fallback.
      - Non-cloud models: convert messages -> raw prompt and call non-streaming chat(), yielding single chunk.
    """
    try:
        from ollama import Client  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "Ollama is not installed. Install with: pip install ollama"
        ) from e

    kwargs = _ollama_client_kwargs(host, timeout_s, api_key)
    client = Client(**kwargs)

    # Mode selection is strict based on model name only.
    if _is_cloud_model(model):
        # Structured stream expected to be supported for cloud models.
        for part in client.chat(
            model=model, messages=messages, options=options or {}, stream=True
        ):
            piece = _extract_content_piece(part)
            if piece:
                yield piece
        return

    # Non-cloud/offline models: send single raw prompt and yield the full response as one chunk.
    raw = _messages_to_raw_prompt(messages)
    fallback_messages = [{"role": "user", "content": raw}]
    yield _extract_content(
        client.chat(model=model, messages=fallback_messages, options=options or {})
    )
    return


def list_models(
    *,
    host: str = OLLAMA_DEFAULT_HOST,
    timeout_s: int = OLLAMA_DEFAULT_TIMEOUT_S,
    api_key: str | None = None,
) -> list[str]:
    """Return model names from Ollama server (local or Cloud when api_key set)."""
    try:
        from ollama import Client  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "Ollama is not installed. Install with: pip install ollama"
        ) from e

    kwargs = _ollama_client_kwargs(host, timeout_s, api_key)
    client = Client(**kwargs)
    resp = client.list()
    # ollama-python returns either dict or object; normalize
    if isinstance(resp, dict):
        models = resp.get("models") or []
        return [
            str(name)
            for m in models
            if isinstance(m, dict) and (name := m.get("model"))
        ]
    models = getattr(resp, "models", None) or []
    out: list[str] = []
    for m in models:
        name = getattr(m, "model", None) or getattr(m, "name", None)
        if name:
            out.append(str(name))
    return out
