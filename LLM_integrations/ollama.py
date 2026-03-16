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
    if any(s in low for s in ["connection refused", "failed to connect", "cannot connect", "connection error"]):
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
        msg = response.get("message", {}) if isinstance(response, dict) else getattr(response, "message", None)
        if msg is None:
            return ""
        if isinstance(msg, dict):
            content = msg.get("content") or msg.get("thinking") or ""
        else:
            content = getattr(msg, "content", None) or getattr(msg, "thinking", None) or ""
        return (content or "") if content is not None else ""
    except Exception:
        return ""


def _extract_content(response: Any) -> str:
    """Get message content from Ollama response (dict or object). Always return a string."""
    return _extract_content_piece(response).strip()


def _ollama_client_kwargs(host: str, timeout_s: int, api_key: str | None) -> dict[str, Any]:
    """Build kwargs for ollama Client (host, timeout, optional Authorization header for Cloud)."""
    kwargs: dict[str, Any] = {"host": host, "timeout": timeout_s}
    if (api_key or "").strip():
        kwargs["headers"] = {"Authorization": f"Bearer {(api_key or '').strip()}"}
    return kwargs


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
        raise ImportError("Ollama is not installed. Install with: pip install ollama") from e

    kwargs = _ollama_client_kwargs(host, timeout_s, api_key)
    client = Client(**kwargs)
    resp = client.chat(model=model, messages=messages, options=options or {})
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
    """
    try:
        from ollama import Client  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise ImportError("Ollama is not installed. Install with: pip install ollama") from e

    kwargs = _ollama_client_kwargs(host, timeout_s, api_key)
    client = Client(**kwargs)
    for part in client.chat(model=model, messages=messages, options=options or {}, stream=True):
        piece = _extract_content_piece(part)
        if piece:
            yield piece


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
        raise ImportError("Ollama is not installed. Install with: pip install ollama") from e

    kwargs = _ollama_client_kwargs(host, timeout_s, api_key)
    client = Client(**kwargs)
    resp = client.list()
    # ollama-python returns either dict or object; normalize
    if isinstance(resp, dict):
        models = resp.get("models") or []
        return [m.get("model") for m in models if isinstance(m, dict) and m.get("model")]
    models = getattr(resp, "models", None) or []
    out: list[str] = []
    for m in models:
        name = getattr(m, "model", None) or getattr(m, "name", None)
        if name:
            out.append(str(name))
    return out

