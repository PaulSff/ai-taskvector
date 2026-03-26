"""
RunWorkflow unit: run a workflow graph from parser action run_workflow or current graph.

Accepts parser_output (from ProcessAgent) with optional run_workflow payload { "action": "run_workflow", "path": "optional path to json" }.
If path is set, loads the workflow from file; otherwise uses the graph input (current graph from inject_graph).
Runs the graph via GraphExecutor and outputs the execution results. Used so the assistant can run the current graph.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.normalizer import load_process_graph_from_file, to_process_graph
from core.schemas.process_graph import ProcessGraph
from core.graph.batch_edits import apply_workflow_edits
from runtime.executor import GraphExecutor
from units.registry import UnitSpec, register_unit

RUN_WORKFLOW_INPUT_PORTS = [("parser_output", "Any"), ("graph", "Any")]
RUN_WORKFLOW_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]


def _build_initial_inputs(graph: ProcessGraph, user_message: str) -> dict[str, dict[str, Any]]:
    """Build initial_inputs for Inject units. inject_graph gets the graph (dict); others get user_message when non-empty.
    When user_message is empty, do not set initial_inputs for other Injects so they use params or Template connection."""
    initial: dict[str, dict[str, Any]] = {}
    msg = (user_message or "").strip()
    graph_dict: dict[str, Any] = (
        graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else {}
    )
    for u in graph.units:
        if u.type == "Inject":
            if u.id == "inject_graph":
                initial[u.id] = {"data": graph_dict}
            elif msg:
                initial[u.id] = {"data": msg}
    return initial


def _run_graph(graph: ProcessGraph, initial_inputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Run graph once via executor; returns outputs."""
    from units.register_env_agnostic import register_env_agnostic_units

    register_env_agnostic_units()
    try:
        from units.data_bi import register_data_bi_units
        register_data_bi_units()
    except Exception:
        pass
    try:
        from units.web import register_web_units
        register_web_units()
    except Exception:
        pass

    executor = GraphExecutor(graph)
    return executor.execute(initial_inputs=initial_inputs or {})


def _extract_parser_edits(parser_output: Any) -> list[dict[str, Any]]:
    """Extract graph edits from parser output (list or dict with `edits`)."""
    if isinstance(parser_output, list):
        return [e for e in parser_output if isinstance(e, dict)]
    if isinstance(parser_output, dict):
        raw = parser_output.get("edits")
        if isinstance(raw, list):
            return [e for e in raw if isinstance(e, dict)]
    return []


def _apply_inline_edits(graph: ProcessGraph, parser_output: Any) -> ProcessGraph:
    """
    Apply inline graph edits before running.

    This ensures mixed action blocks like remove_unit + run_workflow run against
    the edited graph, not the pre-edit snapshot injected into this unit.
    """
    edits = _extract_parser_edits(parser_output)
    if not edits:
        return graph
    g_dict = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else {}
    out = apply_workflow_edits(g_dict, edits)
    if out.get("success") and isinstance(out.get("graph"), dict):
        return to_process_graph(out["graph"], format="dict")
    return graph


def _run_workflow_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """If parser_output has run_workflow: run from path or current graph; else no-op."""
    parser_output = inputs.get("parser_output")
    graph_input = inputs.get("graph")
    user_message = (params.get("user_message") or "").strip() or ""

    if not isinstance(parser_output, dict) or "run_workflow" not in parser_output:
        return ({"data": {}, "error": None}, state)

    payload = parser_output.get("run_workflow")
    if not isinstance(payload, dict):
        return ({"data": {}, "error": None}, state)

    path_val = payload.get("path")
    path_str = path_val.strip() if isinstance(path_val, str) else None
    graph: ProcessGraph | None = None

    if path_str:
        try:
            path = Path(path_str).expanduser().resolve()
            graph = load_process_graph_from_file(path, format="dict")
        except Exception as e:
            return ({"data": {}, "error": f"run_workflow path load failed: {e}"}, state)
    else:
        if graph_input is None:
            return ({"data": {}, "error": "run_workflow: no path and no graph input (current graph required)"}, state)
        try:
            if isinstance(graph_input, ProcessGraph):
                graph = graph_input
            elif isinstance(graph_input, dict):
                graph = to_process_graph(graph_input, format="dict")
            elif hasattr(graph_input, "model_dump"):
                graph = to_process_graph(graph_input.model_dump(by_alias=True), format="dict")
            else:
                return ({"data": {}, "error": "run_workflow: graph input must be dict or ProcessGraph"}, state)
        except Exception as e:
            return ({"data": {}, "error": f"run_workflow graph parse failed: {e}"}, state)

    if graph is None:
        return ({"data": {}, "error": "run_workflow: no graph to run"}, state)

    try:
        graph = _apply_inline_edits(graph, parser_output)
        initial_inputs = _build_initial_inputs(graph, user_message)
        outputs = _run_graph(graph, initial_inputs)
        return ({"data": outputs, "error": None}, state)
    except Exception as e:
        return ({"data": {}, "error": f"run_workflow execute failed: {e}"}, state)


def register_run_workflow() -> None:
    """Register the RunWorkflow unit type."""
    register_unit(UnitSpec(
        type_name="RunWorkflow",
        input_ports=RUN_WORKFLOW_INPUT_PORTS,
        output_ports=RUN_WORKFLOW_OUTPUT_PORTS,
        step_fn=_run_workflow_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Run a workflow from parser run_workflow action: path to JSON or current graph input. Outputs execution results.",
    ))


__all__ = [
    "register_run_workflow",
    "RUN_WORKFLOW_INPUT_PORTS",
    "RUN_WORKFLOW_OUTPUT_PORTS",
]
