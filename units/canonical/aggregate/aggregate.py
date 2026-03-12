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


def _is_empty(val: Any) -> bool:
    """True if value is considered missing for required-key checks (None, empty, or whitespace-only string)."""
    if val is None:
        return True
    if isinstance(val, str) and not (val or "").strip():
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
        missing = [k for k in required if _is_empty(data_in.get(k))]
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
    required = _required_keys(params)
    missing = [k for k in required if _is_empty(data.get(k))]
    error_msg = f"Aggregate: required input(s) missing or empty: {', '.join(missing)}" if missing else ""
    return ({"data": data, "error": error_msg}, state)


def _required_keys(params: dict[str, Any]) -> list[str]:
    """Return list of keys that must be non-empty. Empty if not specified (no required keys)."""
    required = params.get("required_keys")
    if isinstance(required, (list, tuple)) and required:
        return [str(k) for k in required]
    return []


def register_merge() -> None:
    register_unit(UnitSpec(
        type_name="Aggregate",
        input_ports=MERGE_INPUT_PORTS,
        output_ports=MERGE_OUTPUT_PORTS,
        step_fn=_merge_step,
        role=None,
        description="Collects N inputs (Any type) into one data dict for LLM context (e.g. user_message, RAG, graph_summary → Aggregate → Prompt → LLMAgent).",
    ))


__all__ = ["register_merge", "MERGE_INPUT_PORTS", "MERGE_OUTPUT_PORTS"]
