"""
ExportWorkflow unit: export a process graph to Node-RED / PyFlow / n8n format (wraps core.normalizer.export.from_process_graph).

Input: graph (Any) — process graph (dict or ProcessGraph).
Params: format (str) — "node_red" | "pyflow" | "n8n" | "comfyui".
Output: exported (Any) — raw flow dict/list; error (str) — message on failure.
Used by the GUI so export is done via workflow instead of direct Core dependency.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

EXPORT_WORKFLOW_INPUT_PORTS = [("graph", "Any")]
EXPORT_WORKFLOW_OUTPUT_PORTS = [("exported", "Any"), ("error", "str")]


def _export_workflow_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    graph = inputs.get("graph")
    fmt = (params.get("format") or "node_red")
    if isinstance(fmt, str):
        fmt = fmt.strip().lower() or "node_red"
    if graph is None:
        return ({"exported": None, "error": "ExportWorkflow: graph missing"}, state)
    try:
        from core.normalizer import to_process_graph
        from core.normalizer.export import from_process_graph

        if hasattr(graph, "model_dump"):
            pg = graph
        else:
            pg = to_process_graph(graph, format="dict")
        raw = from_process_graph(pg, format=fmt)
        return ({"exported": raw, "error": None}, state)
    except Exception as e:
        return ({"exported": None, "error": str(e)[:200]}, state)


def register_export_workflow() -> None:
    register_unit(UnitSpec(
        type_name="ExportWorkflow",
        input_ports=EXPORT_WORKFLOW_INPUT_PORTS,
        output_ports=EXPORT_WORKFLOW_OUTPUT_PORTS,
        step_fn=_export_workflow_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Export process graph to Node-RED/PyFlow/n8n format (wraps core.normalizer.export.from_process_graph). Params: format.",
    ))


__all__ = ["register_export_workflow", "EXPORT_WORKFLOW_INPUT_PORTS", "EXPORT_WORKFLOW_OUTPUT_PORTS"]
