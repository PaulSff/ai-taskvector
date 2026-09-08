"""Initial inputs, overrides, runtime label, and apply-result refresh for agent chat workflows."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, cast

from pydantic import ValidationError

from agents.tools.types import ParsedActions, ParserOutput
from core.schemas.graph_edit_api import (
    AgentApplyWorkflowEditsResult,
    ApplyWorkflowEditsResult,
    GraphEdit,
)
from core.schemas.primitives import Data, is_object_list, is_string_keyed_dict
from core.schemas.process_graph import ProcessGraph

logger = logging.getLogger(__name__)

def missing_workflow_msg(path: Path) -> str:
    return f"Required workflow file not found: {path}"


async def get_runtime_for_prompts(
    graph: ProcessGraph | None,
) -> Literal["native", "external"]:
    from services.workflows.core_workflows import run_runtime_label

    def _log(msg: str) -> None:
        print(
            f"[get_runtime_for_prompts] {msg} ts={time.time():.3f}",
            flush=True,
        )

    _log(
        f"enter graph_type={type(graph).__name__} "
        + f"graph_is_none={graph is None}"
    )

    if graph is None:
        _log("graph_none -> external")
        return "external"

    r = graph.runtime
    _log(f"read_runtime_field r={r!r}")

    if r in ("native", "external"):
        _log(f"runtime_field_valid -> {r}")
        return r

    _log("runtime_field_invalid_or_missing -> run_runtime_label(graph)")
    t0 = time.time()

    _, is_native = await run_runtime_label(graph)

    _log(
        f"run_runtime_label_done dt={(time.time() - t0):.3f}s "
        + f"is_native={is_native}"
    )

    out: Literal["native", "external"] = (
        "native" if is_native else "external"
    )
    _log(f"return {out}")
    return out


async def refresh_last_graph_apply_result(
    prev: AgentApplyWorkflowEditsResult | None,
    apply_result: ApplyWorkflowEditsResult,
    *,
    supplement_summary: str = "",
) -> AgentApplyWorkflowEditsResult:
    previous_summary = prev.edits_summary.strip() if prev else ""
    supplement = supplement_summary.strip()

    edits_summary = (
        f"{previous_summary}; {supplement}"
        if previous_summary and supplement
        else previous_summary or supplement or "applied"
    )

    return AgentApplyWorkflowEditsResult(
        attempted=True,
        apply_result=apply_result,
        edits_summary=edits_summary,
    )

def normalize_last_apply_result(
    value: object,
) -> AgentApplyWorkflowEditsResult | None:
    if isinstance(value, AgentApplyWorkflowEditsResult):
        return value

    if isinstance(value, ApplyWorkflowEditsResult):
        return AgentApplyWorkflowEditsResult(
            attempted=True,
            apply_result=value,
            edits_summary="",
        )

    if isinstance(value, ProcessGraph):
        return AgentApplyWorkflowEditsResult(
            attempted=True,
            apply_result=ApplyWorkflowEditsResult(
                success=True,
                graph=value,
                error=None,
            ),
            edits_summary="",
        )

    if not isinstance(value, dict):
        return None

    try:
        return AgentApplyWorkflowEditsResult.model_validate(value)
    except ValidationError:
        try:
            inner_result = ApplyWorkflowEditsResult.model_validate(value)
        except ValidationError:
            return None

        return AgentApplyWorkflowEditsResult(
            attempted=True,
            apply_result=inner_result,
            edits_summary="",
        )

async def validate_graph_to_apply_inline(
    graph: ProcessGraph | None,
) -> tuple[ProcessGraph | None, str | None]:
    if graph is None:
        return None, "ValidateGraphToApply: graph missing"

    try:
        validated_graph = ProcessGraph.model_validate(
            graph.model_dump(by_alias=True)
        )
    except ValidationError as exc:
        return None, f"ValidateGraphToApply: invalid graph: {exc}"

    return validated_graph, None


def get_nested_data(outputs: Mapping[str, object], key: str) -> Data:
    value = outputs.get(key)

    if not is_string_keyed_dict(value):
        return {}

    data = value.get("data")

    if not is_string_keyed_dict(data):
        return {}

    return data

def get_str(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)

    return value if isinstance(value, str) else ""

def get_optional_str(data: Mapping[str, object], key: str) -> str | None:
    value = get_str(data, key)
    return value or None

def get_data(data: Mapping[str, object], key: str) -> Data:
    value = data.get(key)

    return value if is_string_keyed_dict(value) else {}


def get_optional_data(data: Mapping[str, object], key: str) -> Data | None:
    value = data.get(key)

    if value is None:
        return None

    return value if is_string_keyed_dict(value) else None


def get_graph(data: Data, key: str = "graph") -> ProcessGraph | None:
    value: object

    # Direct MergeResponse data:
    # {"graph": ...}
    if key in data:
        value = data.get(key)

    # Aggregate unit output:
    # {"data": {"graph": ...}, "error": "..."}
    else:
        aggregate_data = data.get("data")

        if not isinstance(aggregate_data, dict):
            return None

        value = aggregate_data.get(key)

    return value if isinstance(value, ProcessGraph) else None


def get_units_response(outputs: Mapping[str, object]) -> list[Data]:
    value = outputs.get("units_response")

    if not isinstance(value, list):
        return []

    items = cast(list[object], value)

    return [
        item
        for item in items
        if is_string_keyed_dict(item)
    ]

def _unwrap_unit_data(value: object) -> object:
    """
    Unwrap aggregate/unit output of the form:

        {"data": <payload>, "error": <str>}

    Do not unwrap a parser-output dictionary that already contains
    parser-output fields.
    """
    while (
        is_string_keyed_dict(value)
        and "data" in value
        and not any(field in value for field in ("actions", "error"))
    ):
        value = value["data"]

    return value


def get_optional_parser_output(
    data: Mapping[str, object],
    key: str = "parser_output",
) -> ParserOutput | None:
    logger.debug(
        "get_optional_parser_output received key=%r, data=%r",
        key,
        data,
    )

    # Locate the parser output either directly or inside aggregate data.
    if key in data:
        value: object = data.get(key)
    else:
        aggregate_data = data.get("data")

        if not is_string_keyed_dict(aggregate_data):
            return None

        value = aggregate_data.get(key)

    # Unwrap aggregate/unit output.
    value = _unwrap_unit_data(value)

    if value is None:
        return None

    # Already normalized.
    if isinstance(value, ParserOutput):
        return value

    # Support JSON-serialized parser output.
    if isinstance(value, str):
        raw_value = value.strip()

        if not raw_value:
            return None

        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            logger.exception(
                "Invalid serialized parser output: key=%r value=%r",
                key,
                raw_value[:500],
            )
            raise TypeError(
                f"{key!r} must contain valid JSON parser output; "
                f"got non-JSON string: {raw_value[:200]!r}"
            ) from exc

    if not is_string_keyed_dict(value):
        raise TypeError(
            f"{key!r} must be a ParserOutput or string-keyed dictionary; "
            f"got {type(value).__name__}"
        )

    actions_value = value.get("actions", {})

    if not is_string_keyed_dict(actions_value):
        raise TypeError(
            f"{key!r}.actions must be a string-keyed dictionary"
        )

    raw_edits_value = actions_value.get("edits")

    if raw_edits_value is None:
        raw_edits: list[object] = []
    elif is_object_list(raw_edits_value):
        raw_edits = raw_edits_value
    else:
        raise TypeError(
            f"{key!r}.actions.edits must be a list"
        )

    edits: list[GraphEdit] = []

    for raw_edit in raw_edits:
        if isinstance(raw_edit, GraphEdit):
            edits.append(raw_edit)
        elif is_string_keyed_dict(raw_edit):
            try:
                edits.append(GraphEdit.model_validate(raw_edit))
            except ValidationError as exc:
                raise TypeError(
                    f"Invalid {key!r}.actions.edits item: {raw_edit!r}"
                ) from exc
        else:
            raise TypeError(
                f"Each {key!r}.actions.edits item must be a "
                "GraphEdit or string-keyed dictionary"
            )

    error_value = value.get("error")

    return ParserOutput(
        actions=ParsedActions(edits=edits),
        error=error_value if isinstance(error_value, str) else None,
    )
