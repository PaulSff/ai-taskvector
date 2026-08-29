"""
ApplyEdits (Process) unit: applies parsed edits to the current graph.

Inputs: graph (current graph from Trigger), edits (from ProcessAgent), graph_origin (optional, from RagDetectOrigin).
When an edit has action import_workflow and no origin, graph_origin is used as fallback for the resolver.
Outputs: result (content_for_display, graph, edits, kind), status (apply_result), graph (updated graph for downstream e.g. GraphDiff).
"""
from __future__ import annotations

from typing import cast

from core.graph.batch_edits import apply_workflow_edits
from core.graph.summary import graph_summary
from core.normalizer import graph_to_json_object, to_process_graph
from core.normalizer.shared import to_json_value
from core.schemas.primitives import JsonObject, JsonValue, is_json_array, is_json_object
from units.registry import UnitSpec, register_unit

APPLY_EDITS_INPUT_PORTS = [
    ("graph", "ProcessGraph"),
    ("edits", "JsonObject"),
    ("graph_origin", "str"),
]

APPLY_EDITS_OUTPUT_PORTS = [
    ("result", "JsonObject"),
    ("status", "JsonObject"),
    ("graph", "ProcessGraph"),
    ("error", "str"),
]


def _extract_edits(value: object) -> list[JsonObject]:
    if is_json_array(value):
        edits_value = value
    elif is_json_object(value):
        nested_edits = value.get("edits")

        if not is_json_array(nested_edits):
            return []

        edits_value = nested_edits
    else:
        return []

    return [
        edit
        for edit in edits_value
        if is_json_object(edit)
    ]


def _edits_summary(
    edits: list[dict[str, JsonValue]],
) -> str:
    """Short summary of edits for status."""
    parts: list[str] = []

    for edit in edits:
        action = edit.get("action") or "?"

        if action == "no_edit":
            continue

        if action == "add_unit":
            unit = edit.get("unit")
            unit_id: JsonValue = "?"

            if isinstance(unit, dict):
                unit_id = unit.get("id", "?")

            parts.append(f"add_unit {unit_id}")

        elif action == "remove_unit":
            parts.append(
                f"remove_unit {edit.get('unit_id', '?')}"
            )

        elif action == "set_params":
            parts.append(
                f"set_params {edit.get('id', '?')}"
            )

        elif action == "connect":
            parts.append(
                f"connect {edit.get('from', '?')}"
                + f"->{edit.get('to', '?')}"
            )

        else:
            parts.append(str(action))

    return "; ".join(parts)[:200] if parts else ""


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    items = cast(list[object], value)

    return [
        item.strip()
        for item in items
        if isinstance(item, str) and item.strip()
    ]

def _apply_edits_step(
    params: dict[str, object],
    inputs: dict[str, object],
    state: dict[str, object],
    dt: float,
) -> tuple[dict[str, object], dict[str, object]]:
    """Apply edits to graph; return result and status."""
    del dt

    graph = graph_to_json_object(inputs.get("graph"))
    edits = _extract_edits(inputs.get("edits"))

    apply_result: JsonObject = {
        "attempted": False,
        "success": None,
        "error": None,
    }

    result: JsonObject = {
        "kind": "no_edits",
        "content_for_display": "",
        "graph": graph,
        "edits": to_json_value(edits),
    }

    if not edits:
        return (
            {
                "result": result,
                "status": apply_result,
                "graph": graph,
                "error": None,
            },
            state,
        )

    graph_origin = inputs.get("graph_origin")

    if isinstance(graph_origin, str) and graph_origin.strip():
        origin = graph_origin.strip()
        patched_edits: list[JsonObject] = []

        for edit in edits:
            action = edit.get("action")
            existing_origin = edit.get("origin")

            has_origin = (
                isinstance(existing_origin, str)
                and bool(existing_origin.strip())
            )

            if action == "import_workflow" and not has_origin:
                patched_edits.append({
                    **edit,
                    "origin": origin,
                })
            else:
                patched_edits.append(edit)

        edits = patched_edits
        result["edits"] = to_json_value(edits)

    apply_result["attempted"] = True

    allowed: frozenset[str] | None = None

    allowed_values = string_list(
        params.get("allowed_actions")
    )

    if allowed_values:
        allowed = frozenset(allowed_values)


    wf_result = apply_workflow_edits(
        graph,
        edits,
        allowed_actions=allowed,
    )

    if wf_result["success"]:
        apply_result["success"] = True
        result["kind"] = "applied"

        result_graph = wf_result.get("graph")

        if is_json_object(result_graph):
            result["graph"] = result_graph

        summary = _edits_summary(edits)

        if summary:
            apply_result["edits_summary"] = summary
    else:
        apply_result["success"] = False
        apply_result["error"] = (
            wf_result.get("error") or "Apply failed"
        )
        result["kind"] = "apply_failed"

    graph_after = wf_result.get("graph")

    if not is_json_object(graph_after):
        graph_after = graph

    graph_after_process_graph = to_process_graph(
        graph_after,
        format="dict",
    )

    result["last_apply_result"] = {
        **apply_result,
        "graph_after": to_json_value(
            graph_summary(graph_after_process_graph)
        ),
    }

    out_graph = result.get("graph")

    if not is_json_object(out_graph):
        out_graph = graph

    error_value = apply_result.get("error")
    error_string = error_value if isinstance(error_value, str) else None

    return (
        {
            "result": result,
            "status": apply_result,
            "graph": out_graph,
            "error": error_string,
        },
        state,
    )


def register_apply_edits() -> None:
    """Register the ApplyEdits unit type."""
    register_unit(
        UnitSpec(
            type_name="ApplyEdits",
            input_ports=APPLY_EDITS_INPUT_PORTS,
            output_ports=APPLY_EDITS_OUTPUT_PORTS,
            step_fn=_apply_edits_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description=(
                "Applies parsed edits to graph; outputs result and "
                "status (apply_result)."
            ),
        )
    )


__all__ = [
    "APPLY_EDITS_INPUT_PORTS",
    "APPLY_EDITS_OUTPUT_PORTS",
    "register_apply_edits",
]
