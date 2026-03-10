"""
GraphSummary unit: graph → LLM-friendly summary dict.

Input: graph (Any). Output: summary (Any) — same shape as core.graph.summary.graph_summary.
Used in the assistant workflow so the runner injects only the graph; the workflow produces graph_summary and feeds UnitsLibrary + Merge.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

from core.graph.summary import graph_summary as _graph_summary

GRAPH_SUMMARY_INPUT_PORTS = [("graph", "Any")]
GRAPH_SUMMARY_OUTPUT_PORTS = [("summary", "Any")]


def _graph_summary_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Produce LLM-friendly summary from graph."""
    graph = inputs.get("graph")
    summary = _graph_summary(graph)
    return ({"summary": summary}, state)


def register_graph_summary() -> None:
    """Register the GraphSummary unit type."""
    register_unit(UnitSpec(
        type_name="GraphSummary",
        input_ports=GRAPH_SUMMARY_INPUT_PORTS,
        output_ports=GRAPH_SUMMARY_OUTPUT_PORTS,
        step_fn=_graph_summary_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Produces LLM-friendly summary (units, connections, metadata) from a process graph.",
    ))


__all__ = ["register_graph_summary", "GRAPH_SUMMARY_INPUT_PORTS", "GRAPH_SUMMARY_OUTPUT_PORTS"]
