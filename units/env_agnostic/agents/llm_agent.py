"""
LLMAgent unit type: policy node for LLM-based control.

Ports: system_prompt (port 0, from Prompt), user_message (port 1, from Prompt); output action (raw response string).
When executed, calls LLM_integrations.client.chat() and returns the response.
See docs/PROCESS_GRAPH_TOPOLOGY.md §5.2.
"""

from __future__ import annotations

from typing import Any

from runtime.run import INLINE_STATUS_FOR_STREAMING
from runtime.stream_ui_signals import inline_status_stream_chunk
from units.registry import UnitSpec, register_unit

LLMAGENT_INPUT_PORTS = [("system_prompt", "str"), ("user_message", "str")]
LLMAGENT_OUTPUT_PORTS = [("action", "Any"), ("error", "str")]

# Same placeholder as Aggregate/Prompt so we can detect when the pipeline lost the user message.
_USER_MESSAGE_PLACEHOLDER = "(No message provided.)"


def _is_user_message_missing(raw: Any) -> bool:
    """True if user_message is empty or the known placeholder (pipeline did not receive real message)."""
    if raw is None:
        return True
    s = (raw if isinstance(raw, str) else str(raw or "")).strip()
    return not s or s == _USER_MESSAGE_PLACEHOLDER


def _llm_agent_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Call LLM client; return response as action (string). Expects system_prompt and user_message from Prompt unit."""
    raw_system = inputs.get("system_prompt")
    raw_user = inputs.get("user_message")
    system_prompt = (
        raw_system if isinstance(raw_system, str) else str(raw_system or "")
    ).strip() or "You are a helpful agent."
    user_message = (
        raw_user if isinstance(raw_user, str) else str(raw_user or "")
    ).strip() or "Respond with workflow edits if needed."

    # Emit error when user_message was not provided so workflow_errors show it (upstream: inject/merge/prompt).
    input_err: str | None = None
    if _is_user_message_missing(raw_user):
        input_err = (
            "LLMAgent: user_message missing or placeholder (request did not reach the model; "
            "check the units upstream and its params)."
        )

    provider = (params.get("provider") or "ollama").strip()
    provider_lower = provider.lower()
    model_name = (params.get("model_name") or "llama3.2").strip()
    host = (params.get("host") or "http://127.0.0.1:11434").strip()
    try:
        timeout_s = int(params.get("timeout_s") or 120)
    except (TypeError, ValueError):
        timeout_s = 120
    timeout_s = max(60, min(600, timeout_s))

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Do not mutate params; read stream callback and other options immutably.
    stream_cb = params.get("_stream_callback")
    err: str | None = input_err

    try:
        from LLM_integrations import client as llm_client

        # Build provider-agnostic config (accept common API key aliases if present)
        config: dict[str, Any] = {"model": model_name}
        if provider_lower == "ollama":
            config["host"] = host
            for key in ("api_key", "ollama_api_key", "provider_api_key"):
                v = params.get(key)
                if v:
                    config["api_key"] = v
                    break

        options = params.get("options") or {}
        if not isinstance(options, dict):
            options = {}

        started_thinking = False
        if callable(stream_cb):
            try:
                stream_cb(inline_status_stream_chunk(INLINE_STATUS_FOR_STREAMING))
                started_thinking = True
            except Exception:
                started_thinking = False

            parts: list[str] = []
            first_token = True
            try:
                for piece in llm_client.chat_stream(
                    provider=provider,
                    config=config,
                    messages=messages,
                    timeout_s=timeout_s,
                    options=options,
                ):
                    if piece:
                        if first_token:
                            first_token = False
                            try:
                                stream_cb(inline_status_stream_chunk(None))
                                started_thinking = False
                            except Exception:
                                pass
                        parts.append(piece)
                        try:
                            stream_cb(piece)
                        except Exception:
                            pass
            except Exception:
                if started_thinking:
                    try:
                        stream_cb(inline_status_stream_chunk(None))
                    except Exception:
                        pass
                    started_thinking = False
                raise

            response_text = "".join(parts)
        else:
            response_text = llm_client.chat(
                provider=provider,
                config=config,
                messages=messages,
                timeout_s=timeout_s,
                options=options or None,
            )

        action = (response_text or "").strip() or "(No response.)"

    except Exception as e:
        try:
            from LLM_integrations import client as llm_client

            friendly = llm_client.format_exception(provider=provider, e=e).strip()
        except Exception:
            friendly = str(e).strip()[:500]
        err = err or friendly
        action = f"[LLM error: {friendly}]"

    return ({"action": action, "error": err}, state)


def register_llm_agent() -> None:
    """Register LLMAgent in the unit registry."""
    register_unit(
        UnitSpec(
            type_name="LLMAgent",
            input_ports=LLMAGENT_INPUT_PORTS,
            output_ports=LLMAGENT_OUTPUT_PORTS,
            step_fn=_llm_agent_step,
            description="LLM-based policy node: calls LLM_integrations.client.chat(), outputs raw response string.",
        )
    )


__all__ = ["register_llm_agent", "LLMAGENT_INPUT_PORTS", "LLMAGENT_OUTPUT_PORTS"]
