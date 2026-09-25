from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from config.settings import (
    _AGENTS_WORKFLOWS_DIR,
    _CORE_WORKFLOWS_DIR,
    _UNITS_LIBRARY_PATHS_SINGLE,
)
from core.graph import GraphEdit
from core.normalizer.normalizer import to_process_graph
from core.schemas.primitives import (
    Data,
    FormatProcess,
    JsonObject,
    JsonValue,
    RawProcessInput,
    WorkflowInputs,
    WorkflowOutputs,
    is_data,
    is_format_process,
    is_json_document,
    is_json_object,
)
from core.schemas.process_graph import ProcessGraph
from core.schemas.training_config import TrainingConfig
from services.logging import setup_colored_logging

EXECUTION_TIMEOUT_S = 30

logger = setup_colored_logging(logging.DEBUG)

def missing_workflow_msg(path: Path) -> str:
    return f"Required workflow file not found: {path}"


def _run_sync(
    path: Path,
    initial_inputs: WorkflowInputs,
    unit_param_overrides: WorkflowInputs | None = None,
) -> WorkflowOutputs:
    from runtime.run import run_workflow

    return run_workflow(
        path,
        initial_inputs=initial_inputs,
        unit_param_overrides=unit_param_overrides or {},
        format="dict",
        execution_timeout_s=EXECUTION_TIMEOUT_S,
    )


async def _run_async(
    path: Path,
    initial_inputs: WorkflowInputs,
    unit_param_overrides: WorkflowInputs | None = None,
) -> WorkflowOutputs:
    return await asyncio.to_thread(
        _run_sync, path, initial_inputs, unit_param_overrides
    )


def register_env_agnostic_units_sync() -> None:
    """Backward-compatible name: full registry bootstrap (same as run_workflow startup)."""
    try:
        from units.registry import ensure_full_unit_registry

        ensure_full_unit_registry()
    except (ImportError, ModuleNotFoundError):
            pass
    except (OSError, PermissionError, ValueError, TypeError):
        pass


async def register_env_agnostic_units() -> None:
    try:
        from units.registry import ensure_full_unit_registry

        await asyncio.to_thread(ensure_full_unit_registry)
    except (ImportError, ModuleNotFoundError):
            pass
    except (OSError, PermissionError, ValueError, TypeError):
        pass

async def run_graph_summary_inline(graph: ProcessGraph) -> Data:
    g = (
        graph.model_dump(by_alias=True)
        if hasattr(graph, "model_dump")
        else (graph if isinstance(graph, dict) else {})
    )

    path = _CORE_WORKFLOWS_DIR / "graph_summary_single.json"
    if not path.is_file():
        return {"units": [], "connections": []}

    out = await _run_async(path, {"inject_graph": {"data": g}})

    graph_summary = out.get("graph_summary")
    if not is_json_object(graph_summary):
        return {"units": [], "connections": []}

    summary = graph_summary.get("summary")
    if not is_data(summary):
        return {"units": [], "connections": []}

    return summary


async def run_units_library_source_paths_inline(
    graph_summary: Data | None,
    implementation_links_for_types: list[str] | None,
) -> list[str]:
    gs: JsonObject = (
        graph_summary
        if graph_summary is not None and is_json_object(graph_summary)
        else {}
    )

    link: list[JsonValue] = []

    for value in implementation_links_for_types or []:
        item = str(value).strip()
        if item:
            link.append(item)

    if not link or not _UNITS_LIBRARY_PATHS_SINGLE.is_file():
        return []

    unit_param_overrides: WorkflowInputs = {
        "units_library": {
            "implementation_links_for_types": link,
        }
    }

    out = await _run_async(
        _UNITS_LIBRARY_PATHS_SINGLE,
        {"inject_graph_summary": {"data": gs}},
        unit_param_overrides=unit_param_overrides,
    )

    units_library = out.get("units_library")
    if not is_json_object(units_library):
        return []

    raw = units_library.get("source_paths")
    if not isinstance(raw, list):
        return []

    return [
        str(path)
        for path in raw
        if path is not None and str(path).strip()
    ]


async def run_graph_diff_inline(
    prev_graph: ProcessGraph,
    current_graph: ProcessGraph,
) -> str | None:
    prev = (
        prev_graph.model_dump(by_alias=True)
        if hasattr(prev_graph, "model_dump")
        else (prev_graph if isinstance(prev_graph, dict) else {})
    )

    curr = (
        current_graph.model_dump(by_alias=True)
        if hasattr(current_graph, "model_dump")
        else (current_graph if isinstance(current_graph, dict) else {})
    )

    path = _CORE_WORKFLOWS_DIR / "graph_diff_single.json"
    if not path.is_file():
        return None

    out = await _run_async(
        path,
        {
            "inject_prev": {"data": prev},
            "inject_curr": {"data": curr},
        },
    )

    graph_diff = out.get("graph_diff")
    if not is_json_object(graph_diff):
        return None

    diff = graph_diff.get("diff")
    if not diff:
        return None

    result = str(diff).strip()
    return result or None


async def run_load_workflow_inline(
    path_str: str,
    format: str | None = None,
) -> tuple[ProcessGraph | None, str | None]:
    path = _CORE_WORKFLOWS_DIR / "load_workflow_single.json"

    if not path.is_file():
        return None, missing_workflow_msg(path)

    overrides: WorkflowInputs = {}

    if format:
        overrides = {
            "load_workflow": {
                "format": format,
            }
        }

    out = await _run_async(
        path,
        {"inject_path": {"data": path_str}},
        unit_param_overrides=overrides,
    )

    unit_out = out.get("load_workflow")
    if not is_json_object(unit_out):
        return None, None

    raw_graph = unit_out.get("graph")
    raw_error = unit_out.get("error")

    error = str(raw_error) if raw_error is not None else None

    if not is_json_object(raw_graph):
        return None, error

    try:
        graph = to_process_graph(raw_graph, format="dict")
    except (TypeError, ValueError):
        return None, error

    return graph, error


async def run_export_workflow_inline(
    graph: ProcessGraph,
    format: str,
) -> tuple[RawProcessInput, str | None]:
    graph_data = graph.model_dump(by_alias=True)

    path = _CORE_WORKFLOWS_DIR / "export_workflow_single.json"
    if not path.is_file():
        return "", missing_workflow_msg(path)

    unit_param_overrides: WorkflowInputs = {
        "export_workflow": {
            "format": format,
        }
    }

    out = await _run_async(
        path,
        {"inject_graph": {"data": graph_data}},
        unit_param_overrides=unit_param_overrides,
    )

    unit_out = out.get("export_workflow")
    if not is_json_object(unit_out):
        return "", None

    exported = unit_out.get("exported")
    error = unit_out.get("error")

    error_text = str(error) if error is not None else None

    if isinstance(exported, str):
        return exported, error_text

    if is_json_document(exported):
        return exported, error_text

    return "", error_text


async def run_runtime_label_inline(
    graph: ProcessGraph,
) -> tuple[str, bool]:
    path = _CORE_WORKFLOWS_DIR / "runtime_label_single.json"

    if not path.is_file():
        return "canonical", True

    graph_data = graph.model_dump(by_alias=True)

    out = await _run_async(
        path,
        {"inject_graph": {"data": graph_data}},
    )

    unit_out = out.get("runtime_label")
    if not is_json_object(unit_out):
        return "canonical", True

    label = unit_out.get("label", "canonical")
    is_native = unit_out.get("is_native", True)

    return str(label), bool(is_native)


async def run_apply_edits_inline(
    graph: ProcessGraph,
    edits: list[GraphEdit],
    graph_origin: str | None = None,
) -> tuple[ProcessGraph | None, str | None]:
    path = _CORE_WORKFLOWS_DIR / "apply_edits_single.json"

    if not path.is_file():
        return None, missing_workflow_msg(path)

    graph_data = graph.model_dump(by_alias=True)

    edits_data: list[JsonValue] = [
        edit.model_dump(by_alias=True)
        for edit in edits
    ]

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

    out = await _run_async(path, init)

    unit_out = out.get("apply_edits")
    if not is_json_object(unit_out):
        return None, None

    raw_error = unit_out.get("error")
    if raw_error:
        return None, str(raw_error)[:200]

    raw_graph = unit_out.get("graph")
    if not is_json_object(raw_graph):
        return None, None

    try:
        updated_graph = to_process_graph(raw_graph, format="dict")
    except (TypeError, ValueError) as exc:
        return None, str(exc)[:200]

    return updated_graph, None


async def run_apply_training_config_edits_inline(
    training_config: TrainingConfig,
    edits: list[GraphEdit],
) -> tuple[TrainingConfig | None, str | None]:
    cfg = training_config.model_dump(by_alias=True)

    path = _CORE_WORKFLOWS_DIR / "apply_training_config_edits_single.json"
    if not path.is_file():
        return None, missing_workflow_msg(path)

    edits_data: list[JsonValue] = [
        edit.model_dump(by_alias=True)
        for edit in edits
    ]

    init: WorkflowInputs = {
        "inject_training_config": {
            "data": cfg,
        },
        "inject_edits": {
            "data": edits_data,
        },
    }

    out = await _run_async(path, init)

    unit_out = out.get("apply_training_config_edits")
    if not is_json_object(unit_out):
        return None, None

    raw_error = unit_out.get("error")
    if raw_error:
        return None, str(raw_error)[:500]

    merged = unit_out.get("config")
    if not is_json_object(merged):
        return None, None

    try:
        merged_config = TrainingConfig.model_validate(merged)
    except (TypeError, ValueError):
        return None, "Invalid training configuration returned by workflow"

    return merged_config, None


async def run_normalize_graph_inline(
    graph: ProcessGraph,
    format: str = "dict",
) -> tuple[ProcessGraph | None, str | None]:
    path = _CORE_WORKFLOWS_DIR / "normalize_graph_single.json"

    if not path.is_file():
        return None, missing_workflow_msg(path)

    unit_param_overrides: WorkflowInputs = {
        "normalize_graph": {
            "format": format,
        }
    }

    graph_data = graph.model_dump(by_alias=True)

    out = await _run_async(
        path,
        {"inject_graph": {"data": graph_data}},
        unit_param_overrides=unit_param_overrides,
    )

    unit_out = out.get("normalize_graph")
    if not is_json_object(unit_out):
        return None, None

    raw_graph = unit_out.get("graph")
    raw_error = unit_out.get("error")

    error = str(raw_error) if raw_error is not None else None

    if not is_json_object(raw_graph):
        return None, error

    graph_format: FormatProcess = (
        format if is_format_process(format) else "dict"
    )

    try:
        normalized_graph = to_process_graph(
            raw_graph,
            format=graph_format,
        )
    except (TypeError, ValueError) as exc:
        return None, str(exc)

    return normalized_graph, error


def validate_graph_to_apply_for_canvas_inline_sync(
    graph: ProcessGraph,
) -> tuple[ProcessGraph, str | None]:
    """
    Run ``validate_graph_to_apply_single.json`` (Inject → ValidateGraphToApply), then build
    ``ProcessGraph`` for ``set_graph`` / canvas apply.
    """
    def _fail(msg: str) -> tuple[Any, str]:
        logger.error("ValidateGraphToApply error: %s", msg)
        print(f"ValidateGraphToApply error: {msg}")
        return (None, msg)

    if graph is None:
        return _fail("ValidateGraphToApply: graph missing")

    try:
        g = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else graph
    except (AttributeError, TypeError, ValueError) as e:
        return _fail(f"ValidateGraphToApply: model_dump failed: {e}")


    if not isinstance(g, dict):
        return _fail("ValidateGraphToApply: expected dict or model with model_dump")

    path = _CORE_WORKFLOWS_DIR / "validate_graph_to_apply_single.json"
    if not path.is_file():
        return _fail(missing_workflow_msg(path))

    try:
        out = _run_sync(path, {"inject_graph": {"data": g}})
    except (FileNotFoundError, OSError, PermissionError) as e:
        return _fail(f"ValidateGraphToApply: workflow run failed: {e}")
    except (ValueError, TypeError) as e:
        return _fail(f"ValidateGraphToApply: workflow run failed: {e}")


    if not isinstance(out, dict):
        return _fail("ValidateGraphToApply: expected dict output from workflow")

    unit_out = out.get("validate_graph_to_apply") or {}
    if not isinstance(unit_out, dict):
        return _fail("ValidateGraphToApply: expected dict for validate_graph_to_apply output")

    err = unit_out.get("error")
    if err:
        return _fail(str(err))

    gd = unit_out.get("graph")
    if not isinstance(gd, dict):
        return _fail("ValidateGraphToApply: no graph in workflow output")

    try:
        return (ProcessGraph.model_validate(gd), None)
    except (TypeError, ValueError) as e:
        return _fail(f"ValidateGraphToApply: ProcessGraph.model_validate failed: {str(e)[:200]}")


async def validate_graph_to_apply_for_canvas_inline(
    graph: ProcessGraph,
) -> tuple[ProcessGraph, str | None]:
    return await asyncio.to_thread(
        validate_graph_to_apply_for_canvas_inline_sync, graph
    )


def run_clean_text_for_chat_inline_sync(text: str) -> str:
    """
    Run Inject → CleanText to remove fenced markdown/code and JSON-like
    noise from message text.
    """
    from units.semantics import register_semantics_units

    register_semantics_units()

    path = _AGENTS_WORKFLOWS_DIR / "clean_text_chat_single.json"
    raw = text.strip()

    if not path.is_file():
        return raw

    out = _run_sync(
        path,
        {"inject_text": {"data": raw}},
    )

    unit_out = out.get("clean_text")
    if not is_json_object(unit_out):
        return ""

    cleaned_text = unit_out.get("text")
    if cleaned_text is None:
        return ""

    return str(cleaned_text)


async def run_clean_text_for_chat_inline(text: str) -> str:
    return await asyncio.to_thread(run_clean_text_for_chat_inline_sync, text)
