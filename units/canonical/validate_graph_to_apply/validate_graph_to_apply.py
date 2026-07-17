"""
ValidateGraphToApply: validate input against ProcessGraph schema; emit canonical alias dict or error.

Input: graph (Any) — dict or object with model_dump.
Output: graph (Any) — validated dict (by_alias) or None; error (str) on failure.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

VALIDATE_GRAPH_TO_APPLY_INPUT_PORTS = [("graph", "Any")]
VALIDATE_GRAPH_TO_APPLY_OUTPUT_PORTS = [("graph", "Any"), ("error", "str")]


def _validate_graph_to_apply_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    graph = inputs.get("graph")
    if graph is None:
        return ({"graph": None, "error": "ValidateGraphToApply: graph missing"}, state)
    try:
        from core.schemas.process_graph import ProcessGraph

        g = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else graph
        if not isinstance(g, dict):
            return ({"graph": None, "error": "ValidateGraphToApply: expected dict or model with model_dump"}, state)
        pg = ProcessGraph.model_validate(g)
        out = pg.model_dump(by_alias=True)
        return ({"graph": out, "error": None}, state)
    except Exception as e:
        return ({"graph": None, "error": (str(e) or "validation failed")[:500]}, state)


def register_validate_graph_to_apply() -> None:
    register_unit(
        UnitSpec(
            type_name="ValidateGraphToApply",
            input_ports=VALIDATE_GRAPH_TO_APPLY_INPUT_PORTS,
            output_ports=VALIDATE_GRAPH_TO_APPLY_OUTPUT_PORTS,
            step_fn=_validate_graph_to_apply_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description=(
                "Validate graph dict or model_dump-able object against ProcessGraph schema; "
                "output canonical alias dict or error."
            ),
        )
    )


__all__ = [
    "register_validate_graph_to_apply",
    "VALIDATE_GRAPH_TO_APPLY_INPUT_PORTS",
    "VALIDATE_GRAPH_TO_APPLY_OUTPUT_PORTS",
]
