"""Initial inputs, overrides, runtime label, and apply-result refresh for agent chat workflows."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, cast

from pydantic import TypeAdapter, ValidationError

from agents.tools.types import ParsedActions, ParserOutput
from core.schemas.graph_edit_api import (
    AgentApplyWorkflowEditsResult,
    ApplyWorkflowEditsResult,
    ApplyWorkflowEditsStatus,
    GraphEdit,
)
from core.schemas.primitives import (
    Data,
    JsonValue,
    is_object_list,
    is_string_keyed_dict,
)
from core.schemas.process_graph import ProcessGraph
from core.schemas.process_graph_diff import GraphDiffPayload

_GRAPH_DIFF_ADAPTER = TypeAdapter(GraphDiffPayload)

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
    prev: ApplyWorkflowEditsResult | None,
    apply_result: ApplyWorkflowEditsResult,
    *,
    supplement_summary: str = "",
) -> ApplyWorkflowEditsResult:
    previous_summary = (
        (prev.edits_summary or "").strip()
        if prev is not None
        else ""
    )
    supplement = supplement_summary.strip()

    edits_summary = (
        f"{previous_summary}; {supplement}"
        if previous_summary and supplement
        else previous_summary or supplement or "applied"
    )

    return ApplyWorkflowEditsResult(
        attempted=True,
        success=apply_result.success,
        error=apply_result.error,
        graph_after=apply_result.graph_after,
        edits_summary=edits_summary,
    )


def normalize_last_apply_result(
    value: object,
) -> ApplyWorkflowEditsResult | None:
    if isinstance(value, ApplyWorkflowEditsResult):
        return value

    if isinstance(value, ProcessGraph):
        return ApplyWorkflowEditsResult(
            attempted=True,
            success=True,
            error=None,
            graph_after=value,
            edits_summary="",
        )

    if not isinstance(value, Mapping):
        return None

    try:
        return ApplyWorkflowEditsResult.model_validate(value)
    except ValidationError:
        return None



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

def get_bool(data: Mapping[str, object], key: str, default: bool = False) -> bool:
    value = data.get(key)
    return value if isinstance(value, bool) else default

def get_optional_data(data: Mapping[str, object], key: str) -> Data | None:
    value = data.get(key)

    if value is None:
        return None

    return value if is_string_keyed_dict(value) else None


def get_graph(
    data: Data,
    key: str = "graph",
) -> ProcessGraph | None:
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

    if isinstance(value, ProcessGraph):
        return value

    if isinstance(value, dict):
        try:
            return ProcessGraph.model_validate(value)
        except (TypeError, ValueError, ValidationError) as exc:
            logger.warning(
                "Could not parse graph as ProcessGraph: %s",
                exc,
            )
            return None

    return None


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

    if key in data:
        value: object = data.get(key)
    else:
        aggregate_data = data.get("data")

        if not is_string_keyed_dict(aggregate_data):
            return None

        value = aggregate_data.get(key)

    value = _unwrap_unit_data(value)

    if value is None:
        return None

    if isinstance(value, ParserOutput):
        return value

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

    if "actions" in value:
        actions_value = value.get("actions")
    else:
        actions_value = value

    if isinstance(actions_value, ParsedActions):
        parsed_actions = actions_value
    else:
        if not is_string_keyed_dict(actions_value):
            raise TypeError(
                f"{key!r}.actions must be a string-keyed dictionary"
            )

        raw_edits_value = actions_value.get("edits", [])

        if not is_object_list(raw_edits_value):
            raise TypeError(
                f"{key!r}.actions.edits must be a list"
            )

        edits: list[GraphEdit] = []

        for raw_edit in raw_edits_value:
            if isinstance(raw_edit, GraphEdit):
                edits.append(raw_edit)
            elif is_string_keyed_dict(raw_edit):
                try:
                    edits.append(
                        GraphEdit.model_validate(raw_edit)
                    )
                except ValidationError as exc:
                    raise TypeError(
                        f"Invalid {key!r}.actions.edits item: "
                        f"{raw_edit!r}"
                    ) from exc
            else:
                raise TypeError(
                    f"Each {key!r}.actions.edits item must be a "
                    "GraphEdit or string-keyed dictionary"
                )

        raw_tool_actions = actions_value.get(
            "tool_actions",
            {},
        )

        if raw_tool_actions is None:
            raw_tool_actions = {}

        if not is_string_keyed_dict(raw_tool_actions):
            raise TypeError(
                f"{key!r}.actions.tool_actions must be a "
                "string-keyed dictionary"
            )

        tool_actions: dict[str, list[Data]] = {}

        for action_name, raw_values in raw_tool_actions.items():
            if raw_values is None:
                tool_actions[action_name] = []
            elif is_object_list(raw_values):
                tool_actions[action_name] = [
                    cast(Data, raw_value)
                    for raw_value in raw_values
                ]
            else:
                raise TypeError(
                    f"{key!r}.actions.tool_actions"
                    f"[{action_name!r}] must be a list"
                )

        parsed_actions = ParsedActions(
            edits=edits,
            tool_actions=tool_actions,
        )

    error_value = value.get("error")

    normalized = ParserOutput(
        actions=parsed_actions,
        error=error_value if isinstance(error_value, str) else None,
    )

    return normalized


def non_empty_diff(value: object) -> JsonValue | None:
    if isinstance(value, dict):
        filtered_dict: dict[str, JsonValue] = {}

        for key, item in value.items():
            if not isinstance(key, str):
                continue

            cleaned = non_empty_diff(item)

            if cleaned is not None:
                filtered_dict[key] = cleaned

        return filtered_dict or None

    if isinstance(value, list):
        filtered_list: list[JsonValue] = []

        for item in value:
            cleaned = non_empty_diff(item)

            if cleaned is not None:
                filtered_list.append(cleaned)

        return filtered_list or None

    if value is None:
        return None

    if isinstance(value, bool):
        return value if value else None

    if isinstance(value, (int, float)):
        return value

    if isinstance(value, str):
        return value if value.strip() else None

    return None

def get_workflow_edit_apply_result(
    data: Data,
    key: str,
) -> AgentApplyWorkflowEditsResult:
    # Prefer the direct value when present.
    if key in data:
        value = data.get(key)
    else:
        # Aggregate unit output:
        # {"data": {"graph": ...}, "error": "..."}
        aggregate_data = data.get("data")

        if not isinstance(aggregate_data, Mapping):
            logger.debug(
                "Aggregated workflow edit apply result data is missing or invalid: "
                "key=%r aggregate_data_type=%s",
                key,
                type(aggregate_data).__qualname__,
            )
            raise KeyError(f"{key} is missing from data")

        value = aggregate_data.get(key)

    logger.debug(
        "Extracting workflow edit apply result: key=%r value_type=%s value=%r",
        key,
        type(value).__qualname__,
        value,
    )

    if value is None:
        logger.debug(
            "Workflow edit apply result is missing: key=%r",
            key,
        )
        raise KeyError(f"{key} is missing from data")

    if isinstance(value, AgentApplyWorkflowEditsResult):
        logger.debug(
            "Workflow edit apply result already validated: key=%r",
            key,
        )
        return value

    if not isinstance(value, Mapping):
        logger.debug(
            "Workflow edit apply result has invalid type: key=%r type=%s",
            key,
            type(value).__qualname__,
        )
        raise TypeError(f"{key} must be a mapping")

    try:
        result = AgentApplyWorkflowEditsResult.model_validate(value)
    except ValidationError as exc:
        logger.debug(
            "Workflow edit apply result validation failed: key=%r value=%r",
            key,
            value,
            exc_info=True,
        )
        raise TypeError(
            f"{key} must contain a valid AgentApplyWorkflowEditsResult"
        ) from exc

    logger.debug(
        "Workflow edit apply result validated successfully: key=%r result=%r",
        key,
        result,
    )

    return result

def get_apply_workflow_edits_status(
    data: Data,
    key: str,
) -> ApplyWorkflowEditsStatus:
    logger.debug("Reading apply workflow edits status from key=%r", key)

    # Prefer the direct value.
    if key in data:
        value = data.get(key)
    else:
        # Aggregate unit output:
        # {"data": {"status": ...}, "error": "..."}
        aggregate_data = data.get("data")

        if isinstance(aggregate_data, Mapping):
            value = aggregate_data.get(key)
        else:
            value = None

    if value is None:
        logger.debug(
            "No apply workflow edits status found for key=%r; "
            "returning an unattempted status",
            key,
        )
        return ApplyWorkflowEditsStatus(
            attempted=False,
            success=None,
            error=None,
            edits_summary=None,
        )

    if isinstance(value, ApplyWorkflowEditsStatus):
        logger.debug(
            "Apply workflow edits status for key=%r is already validated",
            key,
        )
        return value

    if not isinstance(value, Mapping):
        logger.error(
            "Invalid apply workflow edits status for key=%r: "
            "expected a mapping, got %s",
            key,
            type(value).__name__,
        )
        raise TypeError(f"{key} must be a mapping")

    try:
        status = ApplyWorkflowEditsStatus.model_validate(value)
    except ValidationError as exc:
        logger.error(
            "Invalid ApplyWorkflowEditsStatus data for key=%r: %s",
            key,
            exc,
        )
        raise TypeError(
            f"{key} must contain a valid ApplyWorkflowEditsStatus"
        ) from exc

    logger.debug(
        "Successfully validated apply workflow edits status for key=%r",
        key,
    )
    return status

def get_graph_diff_payload(
    data: Data,
    key: str,
) -> GraphDiffPayload:
    logger.debug("Reading graph diff payload from key=%r", key)

    # Prefer the direct value.
    if key in data:
        value = data.get(key)
    else:
        # Aggregate unit output:
        # {"data": {"graph_diff": ...}, "error": "..."}
        aggregate_data = data.get("data")

        if isinstance(aggregate_data, Mapping):
            value = aggregate_data.get(key)
        else:
            value = None

    if value is None:
        logger.error(
            "Graph diff payload is missing from data for key=%r",
            key,
        )
        raise KeyError(f"{key} is missing from data")

    try:
        payload = _GRAPH_DIFF_ADAPTER.validate_python(value)
    except ValidationError as exc:
        logger.error(
            "Invalid GraphDiffPayload for key=%r: %s",
            key,
            exc,
        )
        raise TypeError(
            f"{key} must contain a valid GraphDiffPayload"
        ) from exc

    logger.debug(
        "Successfully validated graph diff payload for key=%r",
        key,
    )

    return payload
