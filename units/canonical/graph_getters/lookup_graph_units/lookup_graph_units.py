"""lookup_graph_units: graph + unit ids → structured lookup (core.graph.lookup_units)."""
from __future__ import annotations

from typing import Any

from core.graph.lookup_units import lookup_graph_units_data
from units.registry import UnitSpec, register_unit

INPUT_PORTS = [("graph", "Any"), ("ids", "Any")]
OUTPUT_PORTS = [("data", "Any")]


def _graph_to_dict(graph: Any) -> dict[str, Any]:
    """Coerce to dict only; use ``NormalizeGraph`` upstream for schema normalization."""
    if graph is None:
        return {}
    if isinstance(graph, dict):
        return graph
    if hasattr(graph, "model_dump"):
        return graph.model_dump(by_alias=True)
    return {}


def _normalize_unit_ids(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        return [s] if s else []
    if isinstance(raw, dict):
        inner = raw.get("unit_ids")
        if inner is None:
            inner = raw.get("read_code_block_ids")
        if inner is None:
            inner = raw.get("ids")
        return _normalize_unit_ids(inner)
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if isinstance(x, str) and str(x).strip()]
    return []


def _step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    graph_dict = _graph_to_dict(inputs.get("graph"))
    unit_ids = _normalize_unit_ids(inputs.get("ids"))
    data = dict(lookup_graph_units_data(graph_dict, unit_ids))
    types = data.get("canonical_types_without_code_block")
    if not isinstance(types, list):
        types = []
    paths: list[str] = []
    try:
        from units.canonical.units_library.library_builder import collect_source_paths_for_unit_types

        paths = collect_source_paths_for_unit_types([str(t).strip() for t in types if str(t).strip()])
    except Exception:
        paths = []
    primary = paths[0] if paths else ""
    data["implementation_source_paths"] = paths
    data["primary_implementation_path"] = primary
    data["path"] = primary
    return ({"data": data}, state)


def register_lookup_graph_units() -> None:
    register_unit(
        UnitSpec(
            type_name="lookup_graph_units",
            input_ports=INPUT_PORTS,
            output_ports=OUTPUT_PORTS,
            step_fn=_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description=(
                "Graph dict (after NormalizeGraph) + unit ids → code_block_ids, per-unit rows, "
                "canonical_types_without_code_block, needs_implementation_links (core.graph.lookup_units), "
                "plus implementation_source_paths / primary_implementation_path / path for downstream routing."
            ),
        )
    )


__all__ = ["register_lookup_graph_units", "INPUT_PORTS", "OUTPUT_PORTS"]
