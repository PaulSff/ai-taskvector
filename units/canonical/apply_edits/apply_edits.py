"""
ApplyEdits (Process) unit: applies parsed edits to the current graph.

Inputs: graph (current graph from Trigger), edits (from ProcessAgent).
Outputs: result (content_for_display, graph, edits, kind), status (apply_result), graph (updated graph for downstream e.g. GraphDiff).
Used in the assistant workflow: Trigger -> graph; ProcessAgent -> edits; ApplyEdits -> result + status + graph.
"""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

from core.graph.batch_edits import apply_workflow_edits
from core.graph.summary import graph_summary

APPLY_EDITS_INPUT_PORTS = [("graph", "Any"), ("edits", "Any")]
APPLY_EDITS_OUTPUT_PORTS = [("result", "Any"), ("status", "Any"), ("graph", "Any")]


def _edits_summary(edits: list[dict[str, Any]]) -> str:
    """Short summary of edits for status."""
    parts: list[str] = []
    for e in edits:
        if not isinstance(e, dict):
            continue
        action = e.get("action") or "?"
        if action == "no_edit":
            continue
        if action == "add_unit":
            u = e.get("unit") or {}
            parts.append(f"add_unit {u.get('id', '?')}")
        elif action == "remove_unit":
            parts.append(f"remove_unit {e.get('unit_id', '?')}")
        elif action == "connect":
            parts.append(f"connect {e.get('from', '?')}->{e.get('to', '?')}")
        else:
            parts.append(str(action))
    return "; ".join(parts)[:200] if parts else ""


def _apply_edits_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply edits to graph; return result and status."""
    graph = inputs.get("graph")
    edits_raw = inputs.get("edits")

    # Normalize edits: may be list or dict with "edits" key
    edits: list[dict[str, Any]] = []
    if isinstance(edits_raw, list):
        edits = [e for e in edits_raw if isinstance(e, dict)]
    elif isinstance(edits_raw, dict) and "edits" in edits_raw:
        edits = list(edits_raw.get("edits") or [])
        if not isinstance(edits, list):
            edits = []

    if graph is None:
        graph = {"units": [], "connections": []}
    elif hasattr(graph, "model_dump"):
        graph = graph.model_dump(by_alias=True)
    else:
        graph = dict(graph) if isinstance(graph, dict) else {"units": [], "connections": []}

    apply_result: dict[str, Any] = {"attempted": False, "success": None, "error": None}
    result: dict[str, Any] = {
        "kind": "no_edits",
        "content_for_display": "",
        "graph": graph,
        "edits": edits,
    }

    if not edits:
        return (
            {"result": result, "status": apply_result, "graph": graph},
            state,
        )

    apply_result["attempted"] = True
    wf_result = apply_workflow_edits(graph, edits)

    if wf_result["success"]:
        apply_result["success"] = True
        result["kind"] = "applied"
        result["graph"] = wf_result["graph"]
        summary = _edits_summary(edits)
        if summary:
            apply_result["edits_summary"] = summary
    else:
        apply_result["success"] = False
        apply_result["error"] = wf_result.get("error") or "Apply failed"
        result["kind"] = "apply_failed"

    result["last_apply_result"] = {
        **apply_result,
        "graph_after": graph_summary(wf_result.get("graph") or graph),
    }

    out_graph = result["graph"]
    return ({"result": result, "status": apply_result, "graph": out_graph}, state)


def register_apply_edits() -> None:
    """Register the ApplyEdits unit type."""
    register_unit(UnitSpec(
        type_name="ApplyEdits",
        input_ports=APPLY_EDITS_INPUT_PORTS,
        output_ports=APPLY_EDITS_OUTPUT_PORTS,
        step_fn=_apply_edits_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Applies parsed edits to graph; outputs result and status (apply_result).",
    ))


__all__ = [
    "register_apply_edits",
    "APPLY_EDITS_INPUT_PORTS",
    "APPLY_EDITS_OUTPUT_PORTS",
]
