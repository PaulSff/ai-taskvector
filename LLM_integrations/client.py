"""
Provider-agnostic LLM client facade.

The GUI should depend on this module (not directly on a single provider like Ollama).
It dispatches to `LLM_integrations.<provider>.py` adapter modules.

Expected adapter API (recommended):
- chat(messages=[{role, content}], timeout_s=int, options=dict|None, **provider_config) -> str
- (optional) list_models(timeout_s=int, **provider_config) -> list[str]
- (recommended) format_exception(e: Exception) -> str
"""

from __future__ import annotations

import importlib
from typing import Any
from collections.abc import Iterator


class LLMIntegrationError(RuntimeError):
    pass


def _load_provider_module(provider: str):
    name = (provider or "").strip()
    if not name:
        raise LLMIntegrationError("No LLM provider configured.")
    try:
        return importlib.import_module(f"LLM_integrations.{name}")
    except ModuleNotFoundError as e:
        raise LLMIntegrationError(f"Unknown LLM provider: {name!r}") from e


def chat(
    *,
    provider: str,
    config: dict[str, Any] | None,
    messages: list[dict[str, str]],
    timeout_s: int,
    options: dict[str, Any] | None = None,
) -> str:
    """
    Call provider adapter `chat(...)` and return assistant text.
    Retries with a reduced argument set for adapters that don't accept timeout/options.
    """
    mod = _load_provider_module(provider)
    fn = getattr(mod, "chat", None)
    if not callable(fn):
        raise LLMIntegrationError(f"LLM provider {provider!r} does not implement chat().")

    cfg = dict(config or {})
    try:
        return fn(messages=messages, timeout_s=timeout_s, options=options, **cfg)
    except TypeError:
        # Backward-compat for simpler adapters.
        return fn(messages=messages, **cfg)


def chat_stream(
    *,
    provider: str,
    config: dict[str, Any] | None,
    messages: list[dict[str, str]],
    timeout_s: int,
    options: dict[str, Any] | None = None,
) -> Iterator[str]:
    """
    Stream provider adapter output as pieces (partial tokens).

    If the provider doesn't implement streaming, this yields a single chunk (the full response).
    """
    mod = _load_provider_module(provider)
    fn = getattr(mod, "chat_stream", None)
    if callable(fn):
        cfg = dict(config or {})
        try:
            yield from fn(messages=messages, timeout_s=timeout_s, options=options, **cfg)
            return
        except TypeError:
            yield from fn(messages=messages, **cfg)
            return

    # Fallback: non-streaming provider
    yield chat(provider=provider, config=config, messages=messages, timeout_s=timeout_s, options=options)


def list_models(*, provider: str, config: dict[str, Any] | None, timeout_s: int) -> list[str]:
    mod = _load_provider_module(provider)
    fn = getattr(mod, "list_models", None)
    if not callable(fn):
        return []
    cfg = dict(config or {})
    try:
        out = fn(timeout_s=timeout_s, **cfg)
    except TypeError:
        out = fn(**cfg)
    if not isinstance(out, list):
        return []
    return [str(x) for x in out if x]


def format_exception(*, provider: str, e: Exception) -> str:
    """
    Convert an exception to a user-friendly error message.
    Uses provider's `format_exception(e)` if present; otherwise falls back.
    """
    try:
        mod = _load_provider_module(provider)
    except Exception:
        return str(e)

    fmt = getattr(mod, "format_exception", None)
    if callable(fmt):
        try:
            return str(fmt(e))
        except Exception:
            return str(e)

    legacy = getattr(mod, f"format_{provider}_exception", None)
    if callable(legacy):
        try:
            return str(legacy(e))
        except Exception:
            return str(e)

    return f"{provider} error: {str(e).strip()}"

