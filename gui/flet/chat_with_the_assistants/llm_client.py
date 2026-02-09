from __future__ import annotations

from typing import Any

from LLM_integrations import ollama as ollama_integration


def suggest_chat_filename_base(
    *,
    first_message: str,
    host: str,
    model: str,
    timeout_s: int,
) -> str:
    """
    Ask the LLM to suggest a short filename base (snake_case), WITHOUT extension.
    Returns raw model output; caller should sanitize/slugify.
    """
    system = (
        "You generate concise filenames for chat logs. "
        "Return ONLY a short snake_case name (no spaces), WITHOUT extension. "
        "Use 3-8 words max. Example: workflow_roundtrip_execution"
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"User's first message:\n{first_message}"},
    ]
    return ollama_integration.chat(
        host=host,
        model=model,
        messages=messages,
        timeout_s=timeout_s,
        options={"temperature": 0.2, "num_predict": 64},
    )

