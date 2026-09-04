"""
ApplyEdits (Process) unit: applies parsed edits to the current graph.

ParserOutput
    ├── actions: ParsedActions
    │   ├── edits: list[GraphEdit]
    │   └── tool_actions: dict[str, list[Data]]
    └── error

The resulting status behavior is:

No edits:
    attempted=False
    success=None
    error=None

Malformed edit container or item:
    attempted=False
    success=None
    error=<reason>

GraphEdit validation failure:
    attempted=False
    success=None
    error=<validation error>

Workflow application failure:
    attempted=True
    success=False
    error=<application error>

Successful application:
    attempted=True
    success=True
    error=None
"""
from __future__ import annotations

from typing import cast

from pydantic import ValidationError

from core.graph.batch_edits import apply_workflow_edits
from core.graph.summary import graph_summary
from core.normalizer import graph_to_json_object, to_process_graph
from core.normalizer.shared import to_json_value
from core.schemas.graph_edit_api import GraphEdit, MultipleEditsSequential
from core.schemas.primitives import (
    Data,
    JsonObject,
    JsonValue,
    Output,
    is_json_array,
    is_json_object,
)
from units.registry import UnitSpec, register_unit

APPLY_EDITS_INPUT_PORTS = [
    ("graph", "ProcessGraph"),
    ("edits", "ParsedActions"),
    ("graph_origin", "str"),
]

APPLY_EDITS_OUTPUT_PORTS = [
    ("result", "JsonObject"),
    ("status", "JsonObject"),
    ("graph", "ProcessGraph"),
    ("error", "str"),
]


def _extract_edits(
    value: object,
) -> tuple[list[JsonObject], str | None]:
    if is_json_array(value):
        edits_value = value
    elif is_json_object(value):
        nested_edits = value.get("edits")

        if not is_json_array(nested_edits):
            return [], "Expected 'edits' to be an array"

        edits_value = nested_edits
    else:
        return [], (
            "Expected edits to be an array or an object "
            "containing 'edits'"
        )

    edits: list[JsonObject] = []
    invalid_items: list[str] = []

    for index, item in enumerate(edits_value):
        if is_json_object(item):
            edits.append(item)
        else:
            invalid_items.append(
                f"edits[{index}] must be an object"
            )

    if invalid_items:
        return edits, "; ".join(invalid_items)

    return edits, None



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
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
) -> Output:
    """Apply edits to graph; return result and status."""
    del dt

    graph: JsonObject = {}

    apply_result: JsonObject = {
        "attempted": False,
        "success": None,
        "error": None,
    }

    result: JsonObject = {
        "kind": "no_edits",
        "content_for_display": "",
        "graph": graph,
        "edits": [],
    }

    try:
        graph = graph_to_json_object(inputs.get("graph"))
        result["graph"] = graph
    except (TypeError, ValueError) as exc:
        error_string = f"Invalid graph: {exc}"

        apply_result["error"] = error_string
        result["error_reason"] = error_string
        result["last_apply_result"] = {
            **apply_result,
            "graph_after": None,
        }

        return (
            {
                "result": result,
                "status": apply_result,
                "graph": graph,
                "error": error_string,
            },
            state,
        )

    edits, extraction_error = _extract_edits(
        inputs.get("edits")
    )
    result["edits"] = to_json_value(edits)

    if extraction_error:
        apply_result["error"] = extraction_error
        result["error_reason"] = extraction_error
        result["last_apply_result"] = {
            **apply_result,
            "graph_after": None,
        }

        return (
            {
                "result": result,
                "status": apply_result,
                "graph": graph,
                "error": extraction_error,
            },
            state,
        )

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
    # We only need the graph origin in the import_workflow action
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
                patched_edits.append(
                    {
                        **edit,
                        "origin": origin,
                    }
                )
            else:
                patched_edits.append(edit)

        edits = patched_edits
        result["edits"] = to_json_value(edits)

    try:
        validated_edits = [
            GraphEdit.model_validate(edit)
            for edit in edits
        ]
    except ValidationError as exc:
        error_string = str(exc)

        apply_result["error"] = error_string
        result["error_reason"] = error_string
        result["last_apply_result"] = {
            **apply_result,
            "graph_after": None,
        }

        return (
            {
                "result": result,
                "status": apply_result,
                "graph": graph,
                "error": error_string,
            },
            state,
        )

    try:
        graph_process = to_process_graph(
            graph,
            format="dict",
        )
    except (TypeError, ValueError) as exc:
        error_string = f"Invalid graph: {exc}"

        apply_result["error"] = error_string
        result["error_reason"] = error_string
        result["last_apply_result"] = {
            **apply_result,
            "graph_after": None,
        }

        return (
            {
                "result": result,
                "status": apply_result,
                "graph": graph,
                "error": error_string,
            },
            state,
        )

    allowed: frozenset[str] | None = None
    allowed_values = string_list(
        params.get("allowed_actions")
    )

    if allowed_values:
        allowed = frozenset(allowed_values)

    apply_result["attempted"] = True

    wf_result = apply_workflow_edits(
        graph_process,
        MultipleEditsSequential(
            edits=validated_edits,
        ),
        allowed_actions=allowed,
    )

    if wf_result.success:
        apply_result["success"] = True
        result["kind"] = "applied"

        result_graph = wf_result.graph.model_dump(
            mode="python",
            by_alias=True,
            exclude_none=True,
        )

        result["graph"] = to_json_value(result_graph)

        summary = _edits_summary(edits)

        if summary:
            apply_result["edits_summary"] = summary
    else:
        apply_result["success"] = False
        apply_result["error"] = (
            wf_result.error or "Apply failed"
        )
        result["kind"] = "apply_failed"

    result["last_apply_result"] = {
        **apply_result,
        "graph_after": to_json_value(
            graph_summary(wf_result.graph)
        ),
    }

    out_graph = result.get("graph")

    if not is_json_object(out_graph):
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
