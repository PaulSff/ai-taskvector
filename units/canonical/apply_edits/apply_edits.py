"""
ApplyEdits (Process) unit: applies parsed edits to the current graph.

Inputs: graph (current graph from Trigger), edits (from ProcessAgent), graph_origin (optional, from RagDetectOrigin).
When an edit has action import_workflow and no origin, graph_origin is used as fallback for the resolver.
Outputs: result (content_for_display, graph, edits, kind), status (apply_result), graph (updated graph for downstream e.g. GraphDiff).
"""
from __future__ import annotations

from typing import Protocol, cast, runtime_checkable

from core.graph.batch_edits import apply_workflow_edits
from core.graph.graph_edits import JSONValue
from core.graph.summary import graph_summary
from units.registry import UnitSpec, register_unit

APPLY_EDITS_INPUT_PORTS = [
    ("graph", "Any"),
    ("edits", "Any"),
    ("graph_origin", "str"),
]

APPLY_EDITS_OUTPUT_PORTS = [
    ("result", "Any"),
    ("status", "Any"),
    ("graph", "Any"),
    ("error", "str"),
]


@runtime_checkable
class _ModelDumpable(Protocol):
    def model_dump(
        self,
        *,
        by_alias: bool = False,
    ) -> dict[str, JSONValue]:
        ...


def _normalize_graph(value: object) -> dict[str, JSONValue]:
    """Convert a graph value into a JSON-compatible graph dictionary."""
    default_graph: dict[str, JSONValue] = {
        "units": [],
        "connections": [],
    }

    if value is None:
        return default_graph

    if isinstance(value, dict):
        return cast(dict[str, JSONValue], value)

    if isinstance(value, _ModelDumpable):
        dumped = value.model_dump(by_alias=True)
        return dumped

    return default_graph


def _edits_summary(
    edits: list[dict[str, JSONValue]],
) -> str:
    """Short summary of edits for status."""
    parts: list[str] = []

    for edit in edits:
        action = edit.get("action") or "?"

        if action == "no_edit":
            continue

        if action == "add_unit":
            unit = edit.get("unit")
            unit_id: JSONValue = "?"

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


def _apply_edits_step(
    params: dict[str, JSONValue],
    inputs: dict[str, JSONValue],
    state: dict[str, JSONValue],
    dt: float,
) -> tuple[dict[str, JSONValue], dict[str, JSONValue]]:
    """Apply edits to graph; return result and status."""
    del dt

    graph = _normalize_graph(inputs.get("graph"))
    edits_raw = inputs.get("edits")

    edits: list[dict[str, JSONValue]] = []

    if isinstance(edits_raw, list):
        edits = [
            cast(dict[str, JSONValue], edit)
            for edit in edits_raw
            if isinstance(edit, dict)
        ]

    elif isinstance(edits_raw, dict):
        nested_edits = edits_raw.get("edits")

        if isinstance(nested_edits, list):
            edits = [
                cast(dict[str, JSONValue], edit)
                for edit in nested_edits
                if isinstance(edit, dict)
            ]

    apply_result: dict[str, JSONValue] = {
        "attempted": False,
        "success": None,
        "error": None,
    }

    edits_value: list[JSONValue] = [
        cast(JSONValue, edit)
        for edit in edits
    ]

    result: dict[str, JSONValue] = {
        "kind": "no_edits",
        "content_for_display": "",
        "graph": graph,
        "edits": edits_value,
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
        patched: list[dict[str, JSONValue]] = []

        for edit in edits:
            if (
                edit.get("action") == "import_workflow"
                and not (
                    edit.get("origin")
                    and str(edit.get("origin")).strip()
                )
            ):
                patched.append({
                    **edit,
                    "origin": origin,
                })
            else:
                patched.append(edit)

        edits = patched

    apply_result["attempted"] = True

    allowed_raw = params.get("allowed_actions")
    allowed: frozenset[str] | None = None

    if isinstance(allowed_raw, list) and allowed_raw:
        allowed = frozenset(
            value.strip()
            for value in (str(item) for item in allowed_raw)
            if value.strip()
        )

    wf_result = apply_workflow_edits(
        graph,
        edits,
        allowed_actions=allowed,
    )

    if wf_result["success"]:
        apply_result["success"] = True
        result["kind"] = "applied"

        result_graph = wf_result.get("graph")
        if isinstance(result_graph, dict):
            result["graph"] = cast(
                dict[str, JSONValue],
                result_graph,
            )

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
    if not isinstance(graph_after, dict):
        graph_after = graph

    result["last_apply_result"] = {
        **apply_result,
        "graph_after": graph_summary(
            cast(dict[str, JSONValue], graph_after)
        ),
    }

    out_graph = result.get("graph", graph)
    if not isinstance(out_graph, dict):
        out_graph = graph

    error_value = apply_result.get("error")
    error_string = (
        error_value
        if isinstance(error_value, str)
        else None
    )

    return (
        {
            "result": result,
            "status": apply_result,
            "graph": cast(
                dict[str, JSONValue],
                out_graph,
            ),
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
