"""
Aggregate unit: N Any inputs → one data dict.

Used for LLM context (e.g. user_message, RAG, recent_changes, graph_summary → Aggregate → Prompt → LLMAgent).
Separate from Join (observation vector for RL); Aggregate outputs a dict for heterogeneous streams.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

DEFAULT_N = 8
# Optional single "data" input: when provided, pass through (no hardcoded keys). Else collect in_0..in_N.
MERGE_INPUT_PORTS = [("data", "Any")] + [(f"in_{i}", "Any") for i in range(DEFAULT_N)]
MERGE_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]

# Value treated as "missing" for user_message so we can detect and report it.
USER_MESSAGE_PLACEHOLDER = "(No message provided.)"


def _is_empty_or_placeholder(key: str, val: Any) -> bool:
    """True if value is considered missing for required-key checks."""
    if val is None:
        return True
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return True
        if key == "user_message" and s == USER_MESSAGE_PLACEHOLDER:
            return True
    return False


def _merge_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """If input "data" is a dict (pre-built context), pass it through. Else collect in_0..in_N into one dict and only output when fully aggregated.
    Emits error on port "error" when any required_keys entry is missing or empty."""
    data_in = inputs.get("data")
    if isinstance(data_in, dict):
        required = _required_keys(params)
        missing = [k for k in required if _is_empty_or_placeholder(k, data_in.get(k))]
        err = f"Aggregate: required input(s) missing or empty: {', '.join(missing)}" if missing else ""
        return ({"data": data_in, "error": err}, state)
    n = int(params.get("num_inputs", DEFAULT_N))
    n = min(max(n, 1), DEFAULT_N)
    keys = params.get("keys")
    if not isinstance(keys, (list, tuple)) or len(keys) < n:
        keys = [f"in_{i}" for i in range(n)]
    data: dict[str, Any] = {}
    for i in range(n):
        key = str(keys[i]) if i < len(keys) else f"in_{i}"
        val = inputs.get(f"in_{i}")
        data[key] = val if val is not None else ""
    # If user_message is still empty, accept it from input port "data" when present (some paths wire user message to "data").
    if "user_message" in data and (data["user_message"] is None or (isinstance(data["user_message"], str) and not (data["user_message"] or "").strip())):
        data_str = inputs.get("data")
        if isinstance(data_str, str) and (data_str or "").strip():
            data["user_message"] = (data_str or "").strip()
    # When keys were fallback (in_0, in_1, ...), treat in_0 as user_message for presence check so we don't emit a false "required: user_message" error.
    if "user_message" not in data and "in_0" in data and (data.get("in_0") or "").strip():
        data["user_message"] = (data["in_0"] or "").strip()
    # Ensure user_message is never empty so the LLM always sees a request (avoids "please specify what you'd like" when message was dropped).
    if "user_message" in data and (data["user_message"] is None or (isinstance(data["user_message"], str) and not (data["user_message"] or "").strip())):
        data["user_message"] = USER_MESSAGE_PLACEHOLDER
    required = _required_keys(params, keys[:n])
    # For "user_message" required check, also accept in_0 when keys were fallback (in_0, in_1, ...).
    def _val_for_required(k: str) -> Any:
        v = data.get(k)
        if k == "user_message" and _is_empty_or_placeholder(k, v) and (data.get("in_0") or "").strip():
            return data.get("in_0")
        return v
    missing = [k for k in required if _is_empty_or_placeholder(k, _val_for_required(k))]
    error_msg = f"Aggregate: required input(s) missing or empty: {', '.join(missing)}" if missing else ""
    return ({"data": data, "error": error_msg}, state)


def _required_keys(params: dict[str, Any], keys_fallback: list[str] | None = None) -> list[str]:
    """Return list of keys that must be non-empty. Defaults to ['user_message'] if not specified."""
    required = params.get("required_keys")
    if isinstance(required, (list, tuple)) and required:
        return [str(k) for k in required]
    if keys_fallback and "user_message" in keys_fallback:
        return ["user_message"]
    return ["user_message"]


def register_merge() -> None:
    register_unit(UnitSpec(
        type_name="Aggregate",
        input_ports=MERGE_INPUT_PORTS,
        output_ports=MERGE_OUTPUT_PORTS,
        step_fn=_merge_step,
        role=None,
        description="Collects N inputs (Any type) into one data dict for LLM context (e.g. user_message, RAG, graph_summary → Aggregate → Prompt → LLMAgent).",
    ))


__all__ = ["register_merge", "MERGE_INPUT_PORTS", "MERGE_OUTPUT_PORTS", "USER_MESSAGE_PLACEHOLDER"]
