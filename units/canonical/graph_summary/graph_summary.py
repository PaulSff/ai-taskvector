"""
GraphSummary unit: ProcessGraph → LLM-friendly summary dict.

Input: validated ProcessGraph.
Output: summary dict with the shape produced by core.graph.summary.graph_summary.

Used in the agent workflow so the runner injects only the graph; the workflow
produces graph_summary and feeds UnitsLibrary + Merge.
"""

from __future__ import annotations

from typing import cast

from core.graph.summary import graph_summary as _graph_summary
from core.schemas.primitives import Data, Output
from core.schemas.process_graph import ProcessGraph
from units.registry import UnitSpec, register_unit

GRAPH_SUMMARY_INPUT_PORTS = [("graph", "ProcessGraph")]
GRAPH_SUMMARY_OUTPUT_PORTS = [("summary", "dict[str, object]")]


def _as_bool(value: object, *, default: bool = False) -> bool:
    """Convert supported workflow parameter values to bool."""
    if value is None:
        return default

    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}

    return bool(value)


def _source_unit_ids(value: object) -> list[str] | None:
    """Return valid source-unit IDs or None."""
    if not isinstance(value, list):
        return None

    values = cast(list[object], value)
    unit_ids = [item for item in values if isinstance(item, str)]

    return unit_ids or None


def _graph_summary_step(
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
) -> Output:
    """
    Produce an LLM-friendly summary from a validated ProcessGraph.

    The runner may provide a ProcessGraph instance or serialized graph data at
    the unit boundary. Serialized data is validated with ProcessGraph before
    being passed to graph_summary().
    """
    graph_input = inputs.get("graph")
    graph = ProcessGraph.model_validate(graph_input)

    summary = _graph_summary(
        graph,
        include_code_block_source=_as_bool(
            params.get("include_code_block_source"),
        ),
        include_source_for_unit_ids=_source_unit_ids(
            params.get("include_source_for_unit_ids"),
        ),
        include_structure=_as_bool(
            params.get("include_structure"),
            default=True,
        ),
    )

    return {"summary": summary}, state


def register_graph_summary() -> None:
    """Register the GraphSummary unit type."""
    register_unit(
        UnitSpec(
            type_name="GraphSummary",
            input_ports=GRAPH_SUMMARY_INPUT_PORTS,
            output_ports=GRAPH_SUMMARY_OUTPUT_PORTS,
            step_fn=_graph_summary_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description=(
                "Validates a ProcessGraph and produces an LLM-friendly "
                "summary containing units, connections, metadata, comments, "
                "and todo lists."
            ),
        )
    )


__all__ = [
    "GRAPH_SUMMARY_INPUT_PORTS",
    "GRAPH_SUMMARY_OUTPUT_PORTS",
    "register_graph_summary",
]
