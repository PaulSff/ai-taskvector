"""
Import_workflow unit: load a workflow from path or URL, or convert raw graph with origin (via import resolver).

Input: graph — import spec (string path/URL or dict with "source") or raw dict/list when origin is provided.
Optional input: origin — when graph is raw workflow data, use this format to convert to canonical.
Output 0: canonical graph (dict) on success, None on failure.
Output 1: error message (empty on success).
"""
from __future__ import annotations

from typing import Any

from core.graph.import_resolver import load_workflow_to_canonical
from core.normalizer.normalizer import to_process_graph
from units.registry import UnitSpec, register_unit

IMPORT_WORKFLOW_INPUT_PORTS = [("graph", "Any"), ("origin", "str")]
IMPORT_WORKFLOW_OUTPUT_PORTS = [("graph", "Any"), ("error", "str")]


def _parse_input(graph: Any) -> tuple[str, str | None]:
    """Extract (source, origin) from input when graph is a path/source spec."""
    if isinstance(graph, str) and graph.strip():
        return (graph.strip(), None)
    if isinstance(graph, dict):
        source = graph.get("source") or graph.get("path") or graph.get("url")
        if source is not None and str(source).strip():
            origin = graph.get("origin") or graph.get("format")
            return (str(source).strip(), str(origin).strip() or None)
    return ("", None)


def _is_source_spec(graph: Any) -> bool:
    """True if graph is a path/URL or dict with 'source' (load from file/URL)."""
    if isinstance(graph, str) and (graph.strip().startswith("/") or graph.strip().startswith("http")):
        return True
    if isinstance(graph, dict) and ("source" in graph or "path" in graph or "url" in graph):
        return True
    return False


def _import_workflow_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Output 0: canonical graph dict or None; output 1: error string."""
    raw = inputs.get("graph") if inputs else None
    origin_from_port = (inputs or {}).get("origin")
    if isinstance(origin_from_port, str):
        origin_from_port = origin_from_port.strip() or None

    # Raw graph + origin from upstream (e.g. RagDetectOrigin): convert in place
    if origin_from_port and isinstance(raw, (dict, list)):
        fmt = origin_from_port.strip().lower()
        if fmt == "generic" or fmt == "canonical":
            fmt = "dict"
        try:
            graph = to_process_graph(raw, format=fmt)
            out = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else dict(graph)
            return ({"graph": out, "error": ""}, state)
        except Exception as e:
            return ({"graph": None, "error": str(e)}, state)

    # Source path/URL: load and convert via resolver
    source, origin = _parse_input(raw)
    if not source:
        return ({"graph": None, "error": "no source (provide string path/URL or dict with 'source')"}, state)
    canonical, err_msg = load_workflow_to_canonical(source, origin=origin)
    return ({"graph": canonical, "error": err_msg or ""}, state)


def register_import_workflow() -> None:
    """Register the Import_workflow unit type."""
    register_unit(
        UnitSpec(
            type_name="Import_workflow",
            input_ports=IMPORT_WORKFLOW_INPUT_PORTS,
            output_ports=IMPORT_WORKFLOW_OUTPUT_PORTS,
            step_fn=_import_workflow_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description="Load workflow from path or URL via import resolver; output 0 = canonical graph, output 1 = error.",
        )
    )


__all__ = [
    "register_import_workflow",
    "IMPORT_WORKFLOW_INPUT_PORTS",
    "IMPORT_WORKFLOW_OUTPUT_PORTS",
]
