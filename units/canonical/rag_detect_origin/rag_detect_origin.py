"""
RagDetectOrigin unit: detect workflow origin using RAG discriminant heuristics (catalogue excluded).

Input: graph (dict, list, or ProcessGraph) — workflow JSON structure.
Output 0 (origin): one of "n8n" | "node_red" | "canonical" | chat_history | "generic" (catalogue → generic).
Output 1 (graph): same graph passed through (bypass) for downstream wiring.
Output 2 (error): error message if detection failed, else empty string.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

from rag.discriminant import classify_json_for_rag

RAG_DETECT_ORIGIN_INPUT_PORTS = [("graph", "Any")]
RAG_DETECT_ORIGIN_OUTPUT_PORTS = [("origin", "str"), ("graph", "Any"), ("error", "str")]


def _graph_to_data(graph: Any) -> dict | list | None:
    """Normalize graph to dict or list for discriminant (path is not used)."""
    if graph is None:
        return None
    if isinstance(graph, (dict, list)):
        return graph
    if hasattr(graph, "model_dump"):
        return graph.model_dump()
    if hasattr(graph, "dict"):
        return getattr(graph, "dict")()
    return None


def _rag_detect_origin_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Output 0: origin; output 1: graph bypass; output 2: error message or empty."""
    graph = inputs.get("graph") if inputs else None
    err_msg = ""
    try:
        data = _graph_to_data(graph)
        raw = classify_json_for_rag(Path("."), data)
        origin = "generic" if raw == "node_red_catalogue" else raw
    except Exception as e:
        origin = "generic"
        err_msg = str(e)
    return ({"origin": origin, "graph": graph, "error": err_msg}, state)


def register_rag_detect_origin() -> None:
    """Register the RagDetectOrigin unit type."""
    register_unit(
        UnitSpec(
            type_name="RagDetectOrigin",
            input_ports=RAG_DETECT_ORIGIN_INPUT_PORTS,
            output_ports=RAG_DETECT_ORIGIN_OUTPUT_PORTS,
            step_fn=_rag_detect_origin_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description="Detect workflow origin (n8n, node_red, canonical, chat_history, generic) from graph structure; catalogue → generic. Output 0 = origin, output 1 = graph bypass, output 2 = error.",
        )
    )


__all__ = [
    "register_rag_detect_origin",
    "RAG_DETECT_ORIGIN_INPUT_PORTS",
    "RAG_DETECT_ORIGIN_OUTPUT_PORTS",
]
