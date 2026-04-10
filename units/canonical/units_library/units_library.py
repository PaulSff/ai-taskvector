"""
UnitsLibrary unit: builds the filtered units list for the prompt from graph context.

Input: graph_summary (dict, same shape as Merge key). Output: data (formatted string for Units Library section).
Used in the assistant workflow: inject_graph_summary → UnitsLibrary → Merge (units_library key).
Caller no longer injects units_library manually.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

from units.canonical.units_library.library_builder import (
    collect_source_paths_for_unit_types,
    format_units_library_for_prompt,
)

UNITS_LIBRARY_INPUT_PORTS = [("graph_summary", "Any")]
UNITS_LIBRARY_OUTPUT_PORTS = [("data", "str"), ("source_paths", "Any")]


def _units_library_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build Units Library string from graph_summary for the prompt."""
    graph_summary = inputs.get("graph_summary")
    if not isinstance(graph_summary, dict):
        graph_summary = {}
    link_types = params.get("implementation_links_for_types")
    if not isinstance(link_types, list):
        link_types = None
    data = format_units_library_for_prompt(
        graph_summary,
        implementation_links_for_types=link_types,
    )
    paths: list[str] = []
    if isinstance(link_types, list) and link_types:
        paths = collect_source_paths_for_unit_types(link_types)
    return ({"data": data, "source_paths": paths}, state)


def register_units_library() -> None:
    """Register the UnitsLibrary unit type."""
    register_unit(UnitSpec(
        type_name="UnitsLibrary",
        input_ports=UNITS_LIBRARY_INPUT_PORTS,
        output_ports=UNITS_LIBRARY_OUTPUT_PORTS,
        step_fn=_units_library_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Builds filtered units library text for the prompt from graph_summary (runtime + environment).",
    ))


__all__ = ["register_units_library", "UNITS_LIBRARY_INPUT_PORTS", "UNITS_LIBRARY_OUTPUT_PORTS"]
