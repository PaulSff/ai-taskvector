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

import logging
from typing import cast

from pydantic import ValidationError

from agents.tools.types import ParsedActions
from core.graph.batch_edits import apply_workflow_edits
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
from services.logging import setup_colored_logging
from units.registry import UnitSpec, register_unit

APPLY_EDITS_INPUT_PORTS = [
    ("graph", "ProcessGraph"),
    ("actions", "ParsedActions"),
    ("graph_origin", "str"),
]


APPLY_EDITS_OUTPUT_PORTS = [
    ("result", "JsonObject"),
    ("status", "JsonObject"),
    ("graph", "ProcessGraph"),
    ("error", "str"),
]

logger = setup_colored_logging(logging.DEBUG)

def _extract_edits(
    value: object,
) -> tuple[list[JsonObject], str | None]:
    if isinstance(value, ParsedActions):
        edits_value: object = value.edits

    elif is_json_array(value):
        edits_value = value

    elif is_json_object(value):
        nested_edits = value.get("edits")

        if not is_json_array(nested_edits):
            return [], "Expected 'edits' to be an array"

        edits_value = nested_edits

    else:
        return [], (
            "Expected actions to be a ParsedActions object, "
            "an array, or an object containing 'edits'"
        )

    edits: list[JsonObject] = []
    invalid_items: list[str] = []

    for index, item in enumerate(edits_value):
        if isinstance(item, GraphEdit):
            edits.append(
                item.model_dump(
                    mode="python",
                    by_alias=True,
                    exclude_none=True,
                )
            )
        elif is_json_object(item):
            edits.append(item)
        else:
            invalid_items.append(
                f"edits[{index}] must be a GraphEdit or object"
            )

    if invalid_items:
        return edits, "; ".join(invalid_items)

    return edits, None



def _edits_summary(
    edits: list[dict[str, JsonValue]],
) -> str:
    """Return a short human-readable summary of graph edits."""
    parts: list[str] = []

    for edit in edits:
        action = edit.get("action")

        if not isinstance(action, str):
            action = "?"

        if action == "add_unit":
            unit = edit.get("unit")

            if isinstance(unit, dict):
                unit_id = unit.get("id", "?")
                unit_type = unit.get("type", "?")
                parts.append(
                    f"add_unit {unit_id} ({unit_type})"
                )
            else:
                parts.append("add_unit ?")

        elif action == "add_pipeline":
            pipeline = edit.get("pipeline")

            if isinstance(pipeline, dict):
                pipeline_id = pipeline.get("id", "?")
                pipeline_type = pipeline.get("type", "?")
                parts.append(
                    f"add_pipeline {pipeline_id} ({pipeline_type})"
                )
            else:
                parts.append("add_pipeline ?")

        elif action == "remove_unit":
            parts.append(
                f"remove_unit {edit.get('unit_id', '?')}"
            )

        elif action == "set_params":
            parts.append(
                f"set_params {edit.get('id', '?')}"
            )

        elif action in {"connect", "disconnect"}:
            from_id = edit.get("from", "?")
            to_id = edit.get("to", "?")

            parts.append(
                f"{action} {from_id}->{to_id}"
            )

        elif action == "replace_graph":
            units = edit.get("units")
            connections = edit.get("connections")

            unit_count = (
                len(units)
                if isinstance(units, list)
                else "?"
            )
            connection_count = (
                len(connections)
                if isinstance(connections, list)
                else "?"
            )

            parts.append(
                "replace_graph "
                f"({unit_count} units, "
                f"{connection_count} connections)"
            )

        elif action == "replace_unit":
            find_unit = edit.get("find_unit")
            replace_with = edit.get("replace_with")

            find_id = "?"
            replacement_id = "?"
            replacement_type = "?"

            if isinstance(find_unit, dict):
                find_id = find_unit.get("id", "?")

            if isinstance(replace_with, dict):
                replacement_id = replace_with.get("id", "?")
                replacement_type = replace_with.get("type", "?")

            parts.append(
                f"replace_unit {find_id} with "
                f"{replacement_id} ({replacement_type})"
            )

        elif action == "add_code_block":
            code_block = edit.get("code_block")

            if isinstance(code_block, dict):
                unit_id = code_block.get("id", "?")
                language = code_block.get("language", "?")
                parts.append(
                    f"add_code_block {unit_id} ({language})"
                )
            else:
                parts.append("add_code_block ?")

        elif action == "add_comment":
            info = edit.get("info", "?")
            parts.append(f"add_comment {info}")

        elif action == "remove_comment":
            parts.append(
                f"remove_comment {edit.get('comment_id', '?')}"
            )

        elif action == "add_todo_list":
            title = edit.get("title")

            if isinstance(title, str) and title.strip():
                parts.append(f"add_todo_list {title.strip()}")
            else:
                parts.append("add_todo_list")

        elif action == "remove_todo_list":
            parts.append(
                f"remove_todo_list "
                f"{edit.get('todo_list_id', '?')}"
            )

        elif action == "add_task":
            todo_list_id = edit.get("todo_list_id", "?")
            text = edit.get("text")

            if isinstance(text, str) and text.strip():
                parts.append(
                    f"add_task {todo_list_id}: "
                    f"{text.strip()}"
                )
            else:
                parts.append(f"add_task {todo_list_id}")

        elif action == "remove_task":
            parts.append(
                f"remove_task {edit.get('task_id', '?')}"
            )

        elif action == "set_implementer":
            parts.append(
                f"set_implementer {edit.get('task_id', '?')} "
                f"to {edit.get('implementer', '?')}"
            )

        elif action == "set_deadline":
            parts.append(
                f"set_deadline {edit.get('task_id', '?')} "
                f"to {edit.get('deadline', '?')}"
            )

        elif action == "set_curator":
            parts.append(
                f"set_curator {edit.get('task_id', '?')} "
                f"to {edit.get('curator', '?')}"
            )

        elif action == "set_todo_list_title":
            parts.append(
                f"set_todo_list_title "
                f"{edit.get('todo_list_id', '?')} "
                f"to {edit.get('title', '?')}"
            )

        elif action == "mark_completed":
            completed = edit.get("completed", True)
            parts.append(
                f"mark_completed "
                f"{edit.get('task_id', '?')} "
                f"({completed})"
            )

        elif action == "add_environment":
            parts.append(
                f"add_environment {edit.get('env_id', '?')}"
            )

        elif action == "import_workflow":
            source = edit.get("source", "?")
            merge = edit.get("merge", False)

            parts.append(
                f"import_workflow {source}"
                + (" (merge)" if merge else "")
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

    raw_actions = inputs.get("actions")
    graph_origin = inputs.get("graph_origin")

    try:
        graph = graph_to_json_object(inputs.get("graph"))
        result["graph"] = graph

    except (TypeError, ValueError) as exc:
        error_string = f"Invalid graph: {exc}"

        logger.error(
            "ApplyEdits could not load input graph: %s",
            error_string,
        )

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

    edits, extraction_error = _extract_edits(raw_actions)

    result["edits"] = to_json_value(edits)

    if extraction_error:
        logger.warning(
            "ApplyEdits rejected malformed edit input: %s",
            extraction_error,
        )

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
        logger.info(
            "ApplyEdits completed with no edits"
        )

        return (
            {
                "result": result,
                "status": apply_result,
                "graph": graph,
                "error": None,
            },
            state,
        )

    # Add graph origin to import_workflow edits when needed.
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

        logger.warning(
            "ApplyEdits rejected invalid graph edits: "
            "count=%d, error=%s",
            len(edits),
            error_string,
        )

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

        logger.error(
            "ApplyEdits could not normalize graph: %s",
            error_string,
        )

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

        logger.warning(
            "ApplyEdits restricted. Allowed actions: %s",
            ", ".join(sorted(allowed)),
        )

    summary = _edits_summary(edits)

    logger.info(
        "Applying graph edits: count=%d%s",
        len(validated_edits),
        f", summary={summary}" if summary else "",
    )

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

        result_graph = wf_result.graph_after.model_dump(
            mode="python",
            by_alias=True,
            exclude_none=True,
        )

        result["graph"] = to_json_value(result_graph)

        if summary:
            apply_result["edits_summary"] = summary

        logger.info(
            "Graph edits applied successfully: count=%d%s",
            len(validated_edits),
            f", summary={summary}" if summary else "",
        )

    else:
        apply_result["success"] = False
        apply_result["error"] = (
            wf_result.error or "Apply failed"
        )
        result["kind"] = "apply_failed"

        logger.error(
            "Graph edit application failed: count=%d, error=%s",
            len(validated_edits),
            apply_result["error"],
        )

    graph_after = wf_result.graph_after.model_dump(
        mode="python",
        by_alias=True,
        exclude_none=True,
    )

    result["last_apply_result"] = {
        **apply_result,
        "graph_after": to_json_value(graph_after),
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
