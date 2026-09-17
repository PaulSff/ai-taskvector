"""
Publish workflows to the workflow server and await results (GUI never runs workflows directly).

JSON files in this package (under ``workflows/core_workflows/``) and sibling
``workflows/agents_workflows/`` are required.
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from core.normalizer.shared import (
    dump_json_object,
    to_json_value,
    workflow_inputs_to_json_object,
)
from core.schemas import ProcessGraph, TrainingConfig
from core.schemas.graph_edit_api import GraphEdit
from core.schemas.primitives import (
    FormatProcess,
    JsonObject,
    JsonValue,
    WorkflowInputs,
    WorkflowOutputs,
    is_json_object,
    is_json_object_keyed_dict,
    is_model_dumpable,
    is_string,
)
from config.settings import (
    _AGENTS_WORKFLOWS_DIR,
    _CORE_WORKFLOWS_DIR,
    _UNITS_LIBRARY_PATHS_SINGLE,
    get_core_workflows_job_pub_endpoint,
    get_core_workflows_max_concurrent_calls,
    get_core_workflows_response_endpoint,
)
from runtime.run import WorkflowTimeoutError
from services.zmq import (
    ZmqPublisher,
    ZmqSubscriber,
    ZmqSubscriptionConfig,
    ZmqTopics,
)

# ---- fixed endpoint pools (configure N >= max concurrent calls) ----
WORKFLOW_SERVER_ENDPOINT = get_core_workflows_job_pub_endpoint()  # e.g. tcp://127.0.0.1:6679
CORE_WORKFLOWS_RESPONSE_ENDPOINT = get_core_workflows_response_endpoint()      # e.g. tcp://127.0.0.1:xxxx

N = get_core_workflows_max_concurrent_calls()

def _parse_host_port(endpoint: str) -> tuple[str, int]:
    # "tcp://127.0.0.1:6679" -> ("tcp://127.0.0.1", 6679)
    m = re.match(r"^(.*):(\d+)$", endpoint)
    if not m:
        raise ValueError(f"Unexpected endpoint format: {endpoint}")
    return m.group(1), int(m.group(2))

workflow_host, workflow_port = _parse_host_port(WORKFLOW_SERVER_ENDPOINT)
resp_host, resp_port = _parse_host_port(CORE_WORKFLOWS_RESPONSE_ENDPOINT)

# ---- fixed endpoint pools (configure N >= max concurrent calls) ----
JOB_PUB_ENDPOINTS = [f"{workflow_host}:{workflow_port + 2 * i}" for i in range(N)]
RESPONSE_ENDPOINTS = [f"{resp_host}:{resp_port + 2 * i}" for i in range(N)]
RESPONSE_SUB_ENDPOINTS = RESPONSE_ENDPOINTS

def missing_workflow_msg(path: Path) -> str:
    return f"Required workflow file not found: {path}"


# ---- internal slot allocator (no slot in public APIs) ----
_slot_sem = asyncio.Semaphore(N)
_slot_next = 0
_slot_lock = asyncio.Lock()


async def _acquire_slot() -> int:
    global _slot_next
    _ = await _slot_sem.acquire()
    async with _slot_lock:
        slot = _slot_next
        _slot_next = (_slot_next + 1) % N
    return slot


async def _release_slot() -> None:
    _slot_sem.release()


# ---- refactored _publish_and_wait signature: no slot param ----
async def _publish_and_wait(
    path: Path,
    initial_inputs: WorkflowInputs | None = None,
    unit_param_overrides: WorkflowInputs | None = None,
    *,
    format: FormatProcess = "dict",
    execution_timeout_s: float | None = None,
) -> WorkflowOutputs:
    slot = await _acquire_slot()
    try:
        run_id = uuid.uuid4().hex
        wp = path.resolve()

        job_pub = ZmqPublisher(
            pub_endpoint=JOB_PUB_ENDPOINTS[slot],
            topics=ZmqTopics(),
        )

        resp_endpoint = RESPONSE_ENDPOINTS[slot]

        topics = ZmqTopics()
        sub = ZmqSubscriber(
            config=ZmqSubscriptionConfig(
                sub_endpoint=RESPONSE_SUB_ENDPOINTS[slot],
                topics=(topics.token, topics.result, topics.error),
                accept_topics=None,
                rcvtimeo_ms=200,
            )
        )

        final_outputs: JsonObject | None = None
        has_workflow_error = False
        workflow_error = ""

        async def _on_error(_topic: str, payload: JsonObject) -> None:
            nonlocal has_workflow_error, workflow_error
            if payload.get("run_id") != run_id:
                return
            err = payload.get("error")
            workflow_error = err if isinstance(err, str) else str(err)
            has_workflow_error = True

        async def _on_result(_topic: str, payload: JsonObject) -> None:
            nonlocal final_outputs
            if payload.get("run_id") != run_id:
                return
            outs = payload.get("outputs")
            final_outputs = outs if isinstance(outs, dict) else {}

        async def _on_token(_topic: str, _payload: JsonObject) -> None:
            return

        sub.on(topics.token, _on_token)
        sub.on(topics.result, _on_result)
        sub.on(topics.error, _on_error)

        await asyncio.wait_for(sub.start(), timeout=30)

        try:
            job_pub.publish_job(
                run_id=run_id,
                workflow_path=str(wp),
                initial_inputs = workflow_inputs_to_json_object(initial_inputs),
                unit_param_overrides=workflow_inputs_to_json_object(
                    unit_param_overrides
                ),
                format=format,
                response_endpoint=resp_endpoint,
            )

            start = time.monotonic()
            while final_outputs is None and not has_workflow_error:
                if (
                    execution_timeout_s is not None
                    and (time.monotonic() - start) > execution_timeout_s
                ):
                    raise WorkflowTimeoutError(execution_timeout_s)
                await asyncio.sleep(0.01)

        finally:
            await sub.stop()

        if has_workflow_error:
            raise RuntimeError(workflow_error)

        return final_outputs or {}
    finally:
        await _release_slot()


async def run_graph_summary(graph: ProcessGraph) -> dict[str, object]:
    """Run the GraphSummary workflow for a validated ProcessGraph."""
    path = _CORE_WORKFLOWS_DIR / "graph_summary_single.json"
    if not path.is_file():
        return {"units": [], "connections": []}

    graph_data = graph.model_dump(
        mode="json",
        by_alias=True,
    )

    out = await _publish_and_wait(
        path,
        {"inject_graph": {"data": graph_data}},
        format="dict",
    )

    graph_summary_output = out.get("graph_summary")
    if not isinstance(graph_summary_output, dict):
        return {"units": [], "connections": []}

    summary = graph_summary_output.get("summary")
    if not isinstance(summary, dict):
        return {"units": [], "connections": []}

    return cast(dict[str, object], summary)


async def run_units_library_source_paths(
    graph_summary: dict[str, object] | None,
    implementation_links_for_types: list[str] | None,
) -> list[str]:
    """
    Run units_library_paths_single.json:
    UnitsLibrary → source_paths.

    The registry is already filled by the server run. This is used by
    Workflow Designer follow-ups instead of importing units.* in the GUI layer.
    """

    gs = (
        cast(dict[str, JsonValue], graph_summary)
        if isinstance(graph_summary, dict)
        else {}
    )

    link = [
        str(value).strip()
        for value in (implementation_links_for_types or [])
        if str(value).strip()
    ]

    if not link or not _UNITS_LIBRARY_PATHS_SINGLE.is_file():
        return []

    initial_inputs: WorkflowInputs = {
        "inject_graph_summary": {
            "data": gs,
        }
    }

    unit_param_overrides: WorkflowInputs = {
        "units_library": {
            "implementation_links_for_types": cast(JsonValue, link),
        }
    }

    out = await _publish_and_wait(
        _UNITS_LIBRARY_PATHS_SINGLE,
        initial_inputs=initial_inputs,
        unit_param_overrides=unit_param_overrides,
        format="dict",
    )

    units_library = out.get("units_library")

    if not isinstance(units_library, dict):
        return []

    raw = units_library.get("source_paths")

    if not isinstance(raw, list):
        return []

    return [
        str(path)
        for path in raw
        if path is not None and str(path).strip()
    ]


async def run_graph_diff(
    prev_graph: ProcessGraph | None,
    current_graph: ProcessGraph | None,
) -> str | None:
    """Run GraphDiff workflow; return diff string or None."""

    if prev_graph is None or current_graph is None:
        return None

    if not is_model_dumpable(prev_graph):
        return None

    if not is_model_dumpable(current_graph):
        return None

    prev: JsonObject = prev_graph.model_dump(by_alias=True)
    curr: JsonObject = current_graph.model_dump(by_alias=True)

    path = _CORE_WORKFLOWS_DIR / "graph_diff_single.json"
    if not path.is_file():
        return None

    inputs: WorkflowInputs = {
        "inject_prev": {"data": prev},
        "inject_curr": {"data": curr},
    }

    out: JsonObject = await _publish_and_wait(
        path,
        inputs,
        format="dict",
    )

    graph_diff = out.get("graph_diff")
    if not is_json_object_keyed_dict(graph_diff):
        return None

    diff = graph_diff.get("diff")
    if diff is None:
        return None

    result = str(diff).strip()
    return result or None



async def run_load_workflow(
    path_str: str,
    format: str | None = None,
) -> tuple[JsonObject | None, str | None]:
    """Run LoadWorkflow; return (graph_dict, error). No Core import in caller."""
    path = _CORE_WORKFLOWS_DIR / "load_workflow_single.json"

    if not path.is_file():
        return None, missing_workflow_msg(path)

    overrides: WorkflowInputs = {}

    if format is not None:
        overrides["load_workflow"] = {
            "format": format,
        }

    out = await _publish_and_wait(
        path,
        {"inject_path": {"data": path_str}},
        unit_param_overrides=overrides,
        format="dict",
    )

    unit_out = out.get("load_workflow")

    if not isinstance(unit_out, dict):
        return None, "LoadWorkflow returned no output"

    graph = unit_out.get("graph")
    error = unit_out.get("error")

    graph_dict = graph if isinstance(graph, dict) else None
    error_string = error if isinstance(error, str) else None

    return graph_dict, error_string



async def run_export_workflow(
    graph: ProcessGraph,
    format: str,
) -> tuple[JsonValue | None, str | None]:
    """Run ExportWorkflow; return (exported value, error). No Core import in caller."""
    serialized_graph = to_json_value(
        graph.model_dump(
            mode="python",
            by_alias=True,
            exclude_none=True,
        )
    )

    if not is_json_object(serialized_graph):
        return None, "ExportWorkflow: graph serialization failed"

    path = _CORE_WORKFLOWS_DIR / "export_workflow_single.json"

    if not path.is_file():
        return None, missing_workflow_msg(path)

    workflow_inputs: WorkflowInputs = {
        "inject_graph": {
            "data": serialized_graph,
        },
    }

    unit_param_overrides: WorkflowInputs = {
        "export_workflow": {
            "format": format,
        },
    }

    out = await _publish_and_wait(
        path,
        workflow_inputs,
        unit_param_overrides=unit_param_overrides,
        format="dict",
    )

    unit_out = out.get("export_workflow")

    if not is_json_object(unit_out):
        return None, "ExportWorkflow returned no output"

    exported = unit_out.get("exported")
    error = unit_out.get("error")

    return (
        exported,
        error if isinstance(error, str) else None,
    )


async def run_runtime_label(
    graph: ProcessGraph,
) -> tuple[str, bool]:
    """Run RuntimeLabel workflow; return (label, is_native)."""
    serialized_graph = to_json_value(
        graph.model_dump(
            mode="python",
            by_alias=True,
            exclude_none=True,
        )
    )

    if not is_json_object(serialized_graph):
        return "canonical", True

    path = _CORE_WORKFLOWS_DIR / "runtime_label_single.json"

    if not path.is_file():
        return "canonical", True

    workflow_inputs: WorkflowInputs = {
        "inject_graph": {
            "data": serialized_graph,
        },
    }

    out = await _publish_and_wait(
        path,
        workflow_inputs,
        format="dict",
    )

    unit_out = out.get("runtime_label")

    if not is_json_object(unit_out):
        return "canonical", True

    label = unit_out.get("label")
    is_native = unit_out.get("is_native")

    return (
        label if isinstance(label, str) else "canonical",
        is_native if isinstance(is_native, bool) else True,
    )


async def run_apply_edits(
    graph: ProcessGraph,
    edits: list[GraphEdit],
    graph_origin: str | None = None,
) -> tuple[JsonObject | None, str | None]:
    """Run ApplyEdits workflow; return (graph_dict, error). No Core import in caller."""

    graph_data = dump_json_object(graph)

    serialized_edits: list[JsonObject] = [
        dump_json_object(edit) for edit in edits
    ]

    # Recursive generic aliases use invariant list types. Convert explicitly
    # at the JSON serialization boundary.
    edits_data = cast(list[JsonValue], serialized_edits)

    path = _CORE_WORKFLOWS_DIR / "apply_edits_single.json"
    if not path.is_file():
        return None, missing_workflow_msg(path)

    init: WorkflowInputs = {
        "inject_graph": {
            "data": graph_data,
        },
        "inject_edits": {
            "data": edits_data,
        },
        "inject_origin": {
            "data": graph_origin or "",
        },
    }

    out: JsonObject = await _publish_and_wait(
        path,
        init,
        format="dict",
    )

    unit_out = out.get("apply_edits")
    if not is_json_object(unit_out):
        return None, "Invalid apply_edits workflow output"

    error = unit_out.get("error")
    if error:
        return None, str(error)[:200]

    graph_out = unit_out.get("graph")
    if not is_json_object(graph_out):
        return None, "ApplyEdits workflow returned an invalid graph"

    return graph_out, None


async def run_apply_training_config_edits(
    training_config: TrainingConfig,
    edits: list[JsonObject],
) -> tuple[JsonObject | None, str | None]:
    """Run ApplyTrainingConfigEdits workflow; return (config_dict, error)."""

    if not is_model_dumpable(training_config):
        return None, "Invalid training config"

    cfg = training_config.model_dump(by_alias=True)
    if not is_json_object(cfg):
        return None, "Training config is not a valid JSON object"

    # list is invariant, so explicitly narrow it to the recursive JSON type.
    edits_data = cast(list[JsonValue], edits)

    path = _CORE_WORKFLOWS_DIR / "apply_training_config_edits_single.json"
    if not path.is_file():
        return None, missing_workflow_msg(path)

    init: WorkflowInputs = {
        "inject_training_config": {
            "data": cfg,
        },
        "inject_edits": {
            "data": edits_data,
        },
    }

    out: JsonObject = await _publish_and_wait(
        path,
        init,
        format="dict",
    )

    unit_out = out.get("apply_training_config_edits")
    if not is_json_object(unit_out):
        return None, "Invalid apply_training_config_edits workflow output"

    error = unit_out.get("error")
    if error:
        return None, str(error)[:500]

    merged = unit_out.get("config")
    if not is_json_object(merged):
        return None, None

    return merged, None


async def run_normalize_graph(
    graph: ProcessGraph | None,
    format: FormatProcess = "dict",
) -> tuple[JsonObject | None, str | None]:
    """Run the NormalizeGraph workflow and return (graph_dict, error)."""

    if graph is None:
        return None, "NormalizeGraph: graph missing"

    graph_data: JsonObject = graph.model_dump(by_alias=True)

    path = _CORE_WORKFLOWS_DIR / "normalize_graph_single.json"
    if not path.is_file():
        return None, missing_workflow_msg(path)

    inputs: WorkflowInputs = {
        "inject_graph": {
            "data": graph_data,
        }
    }

    out: JsonObject = await _publish_and_wait(
        path,
        inputs,
        unit_param_overrides={
            "normalize_graph": {
                "format": format,
            }
        },
        format="dict",
    )

    unit_output = out.get("normalize_graph")
    if not is_json_object(unit_output):
        return None, None

    normalized_graph = unit_output.get("graph")
    error = unit_output.get("error")

    result_graph = normalized_graph if is_json_object(normalized_graph) else None
    result_error = error if is_string(error) else None

    return result_graph, result_error


async def validate_graph_to_apply_for_canvas(
    graph: ProcessGraph | None,
) -> tuple[ProcessGraph | None, str | None]:
    if graph is None:
        return None, "ValidateGraphToApply: graph missing"

    graph_data: JsonObject = graph.model_dump(by_alias=True)

    path = _CORE_WORKFLOWS_DIR / "validate_graph_to_apply_single.json"
    if not path.is_file():
        return None, missing_workflow_msg(path)

    inputs: WorkflowInputs = {
        "inject_graph": {
            "data": graph_data,
        }
    }

    out: JsonObject = await _publish_and_wait(
        path,
        inputs,
        format="dict",
    )

    unit_output = out.get("validate_graph_to_apply")
    if not is_json_object(unit_output):
        return (
            None,
            "ValidateGraphToApply: no workflow output",
        )

    error = unit_output.get("error")
    if error:
        error_text = str(error)
        print(
            "validate_graph_to_apply_for_canvas workflow error:",
            error_text,
        )
        return None, error_text

    graph_data_output = unit_output.get("graph")
    if not is_json_object(graph_data_output):
        return (
            None,
            "ValidateGraphToApply: no graph in workflow output",
        )

    try:
        validated_graph = ProcessGraph.model_validate(graph_data_output)
    except ValidationError as exc:
        return None, f"ValidateGraphToApply: invalid graph: {exc}"

    return validated_graph, None


async def run_clean_text_for_chat(text: str) -> str:
    """
    Run Inject → CleanText (units/semantics/clean_text) to remove fenced
    markdown/code and JSON-like noise from message text for history and
    previous-turn prompts.
    """
    from units.semantics import register_semantics_units

    register_semantics_units()

    path = _AGENTS_WORKFLOWS_DIR / "clean_text_chat_single.json"
    raw = text or ""

    if not path.is_file():
        return raw.strip()

    out = await _publish_and_wait(
        path,
        {"inject_text": {"data": raw}},
        format="dict",
    )
    unit_out = cast(Mapping[str, object], out.get("clean_text") or {})
    return str(unit_out.get("text") or "")
