from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import requests

LLAMA_SERVE_DEFAULT_HOST = "http://127.0.0.1:8080"
LLAMA_SERVE_DEFAULT_TIMEOUT_S = 300


def format_llama_exception(e: Exception) -> str:
    msg = str(e).strip()
    low = msg.lower()

    if any(s in low for s in ["connection refused", "failed to connect", "cannot connect", "connection error"]):
        return (
            "Couldn't connect to the llama.cpp server at the configured host. "
            "Make sure `llama serve` is running on port 8080."
        )
    if "timeout" in low or "timed out" in low:
        return "Request timed out. Try again or reduce generation settings (e.g., max_tokens / context)."
    if "404" in low:
        return "Endpoint not found. Check the server route (e.g., /v1/chat/completions and /v1/models)."
    if "out of memory" in low or "oom" in low:
        return "Server ran out of memory. Try a smaller model or smaller context."
    return f"llama.cpp server error: {msg}"


def format_exception(e: Exception) -> str:
    return format_llama_exception(e)


def _headers(api_key: str | None) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if (api_key or "").strip():
        h["Authorization"] = f"Bearer {(api_key or '').strip()}"
    return h


def _extract_content_piece_openai_stream(chunk: Any) -> str:
    # OpenAI streaming shape: {"choices":[{"delta":{"content":"..."}}]}
    if not isinstance(chunk, dict):
        return ""
    choices = chunk.get("choices") or []
    if not choices:
        return ""
    c0 = choices[0] or {}
    delta = c0.get("delta") or {}
    if isinstance(delta, dict):
        return delta.get("content") or ""
    return ""


def _extract_content_openai_response(resp: Any) -> str:
    # OpenAI non-stream shape: {"choices":[{"message":{"content":"..."}}]}
    if not isinstance(resp, dict):
        return ""
    choices = resp.get("choices") or []
    if not choices:
        return ""
    c0 = choices[0] or {}
    msg = c0.get("message") or {}
    if isinstance(msg, dict):
        return msg.get("content") or ""
    return ""


def chat(
    *,
    host: str = LLAMA_SERVE_DEFAULT_HOST,
    model: str,
    messages: list[dict[str, str]],
    timeout_s: int = LLAMA_SERVE_DEFAULT_TIMEOUT_S,
    options: dict[str, Any] | None = None,
    api_key: str | None = None,
) -> str:
    """
    Call llama.cpp server (llama serve) via OpenAI-compatible /v1/chat/completions.
    Returns assistant content as a string.

    Common options:
      - max_tokens
      - temperature
      - top_p
      - stop
    """
    url = f"{host.rstrip('/')}/v1/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        **(options or {}),
    }

    try:
        r = requests.post(
            url,
            headers=_headers(api_key),
            data=json.dumps(payload),
            timeout=timeout_s,
        )
        r.raise_for_status()
        return _extract_content_openai_response(r.json())
    except Exception as e:
        raise RuntimeError(format_llama_exception(e)) from e


def chat_stream(
    *,
    host: str = LLAMA_SERVE_DEFAULT_HOST,
    model: str,
    messages: list[dict[str, str]],
    timeout_s: int = LLAMA_SERVE_DEFAULT_TIMEOUT_S,
    options: dict[str, Any] | None = None,
    api_key: str | None = None,
) -> Iterator[str]:
    """
    Stream tokens from llama.cpp server (SSE from /v1/chat/completions with stream=true).
    Yields incremental content pieces; caller should concatenate.
    """
    url = f"{host.rstrip('/')}/v1/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        **(options or {}),
    }

    try:
        with requests.post(
            url,
            headers=_headers(api_key),
            data=json.dumps(payload),
            timeout=timeout_s,
            stream=True,
        ) as r:
            r.raise_for_status()

            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue

                # SSE format: "data: {json}\n\n"
                if not line.startswith("data:"):
                    continue

                data_str = line[len("data:") :].strip()
                if data_str == "[DONE]":
                    return

                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                piece = _extract_content_piece_openai_stream(chunk)
                if piece:
                    yield piece
    except Exception as e:
        raise RuntimeError(format_llama_exception(e)) from e


def list_models(
    *,
    host: str = LLAMA_SERVE_DEFAULT_HOST,
    timeout_s: int = LLAMA_SERVE_DEFAULT_TIMEOUT_S,
    api_key: str | None = None,
) -> list[str]:
    """
    Returns model ids from /v1/models (OpenAI-compatible).
    Your server may return {"data": []} if models aren't listed; then [] is returned.
    """
    url = f"{host.rstrip('/')}/v1/models"

    try:
        r = requests.get(url, headers=_headers(api_key), timeout=timeout_s)
        r.raise_for_status()
        data = r.json()

        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []

        out: list[str] = []
        for item in items:
            if isinstance(item, dict) and item.get("id"):
                out.append(str(item["id"]))
        return out
    except Exception as e:
        raise RuntimeError(format_llama_exception(e)) from e
