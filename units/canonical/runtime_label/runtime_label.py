"""
RuntimeLabel unit: detect runtime label from graph (wraps core.normalizer.runtime_detector.runtime_label).

Input: graph (Any) — process graph (dict or ProcessGraph).
Output: label (str) — e.g. "canonical" | "node_red" | "n8n" | "pyflow" | "dict"; is_native (bool) — True if canonical.
Used by the GUI and chat so runtime detection is done via workflow instead of direct Core dependency.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

RUNTIME_LABEL_INPUT_PORTS = [("graph", "Any")]
RUNTIME_LABEL_OUTPUT_PORTS = [("label", "str"), ("is_native", "Any")]


def _runtime_label_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    graph = inputs.get("graph")
    try:
        from core.normalizer.runtime_detector import is_canonical_runtime, runtime_label

        label = runtime_label(graph) if graph is not None else "canonical"
        is_native = is_canonical_runtime(graph) if graph is not None else True
        return ({"label": str(label), "is_native": bool(is_native)}, state)
    except Exception:
        return ({"label": "canonical", "is_native": True}, state)


def register_runtime_label() -> None:
    register_unit(UnitSpec(
        type_name="RuntimeLabel",
        input_ports=RUNTIME_LABEL_INPUT_PORTS,
        output_ports=RUNTIME_LABEL_OUTPUT_PORTS,
        step_fn=_runtime_label_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Detect runtime label from graph (canonical, node_red, n8n, etc.) and is_native. Wraps core.normalizer.runtime_detector.",
    ))


__all__ = ["register_runtime_label", "RUNTIME_LABEL_INPUT_PORTS", "RUNTIME_LABEL_OUTPUT_PORTS"]
