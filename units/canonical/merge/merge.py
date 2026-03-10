"""
Merge unit: N Any inputs → one data dict.

Used for LLM context (e.g. user_message, RAG, recent_changes, graph_summary → Merge → Prompt → LLMAgent).
Separate from Join (observation vector for RL); Merge outputs a dict for heterogeneous streams.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

DEFAULT_N = 8
MERGE_INPUT_PORTS = [(f"in_{i}", "Any") for i in range(DEFAULT_N)]
MERGE_OUTPUT_PORTS = [("data", "Any")]


def _merge_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Collect in_0..in_N into a single dict (optional param keys for key names)."""
    n = int(params.get("num_inputs", DEFAULT_N))
    n = min(max(n, 1), DEFAULT_N)
    keys = params.get("keys")
    if not isinstance(keys, (list, tuple)) or len(keys) < n:
        keys = [f"in_{i}" for i in range(n)]
    data: dict[str, Any] = {}
    for i in range(n):
        key = str(keys[i]) if i < len(keys) else f"in_{i}"
        data[key] = inputs.get(f"in_{i}")
    return ({"data": data}, state)


def register_merge() -> None:
    register_unit(UnitSpec(
        type_name="Merge",
        input_ports=MERGE_INPUT_PORTS,
        output_ports=MERGE_OUTPUT_PORTS,
        step_fn=_merge_step,
        role=None,
        description="Collects N inputs (Any type) into one data dict for LLM context (e.g. user_message, RAG, graph_summary → Merge → Prompt → LLMAgent).",
    ))


__all__ = ["register_merge", "MERGE_INPUT_PORTS", "MERGE_OUTPUT_PORTS"]
