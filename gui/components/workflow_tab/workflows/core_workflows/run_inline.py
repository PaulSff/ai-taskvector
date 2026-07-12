from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
import logging

from core.schemas.process_graph import ProcessGraph

_CORE_WORKFLOWS_DIR = Path(__file__).resolve().parent
_agents_WORKFLOWS_DIR = _CORE_WORKFLOWS_DIR.parent / "agents_workflows"

_UNITS_LIBRARY_PATHS_SINGLE = _agents_WORKFLOWS_DIR / "units_library_paths_single.json"

EXECUTION_TIMEOUT_S = 30

logger = logging.getLogger(__name__)



def _missing_workflow_msg(path: Path) -> str:
    return f"Required workflow file not found: {path}"


def _run_sync(
    path: Path,
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
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
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _run_sync, path, initial_inputs, unit_param_overrides
    )


def register_env_agnostic_units_sync() -> None:
    """Backward-compatible name: full registry bootstrap (same as run_workflow startup)."""
    try:
        from units.registry import ensure_full_unit_registry

        ensure_full_unit_registry()
    except Exception:
        pass


async def register_env_agnostic_units() -> None:
    try:
        from units.registry import ensure_full_unit_registry

        await asyncio.to_thread(ensure_full_unit_registry)
    except Exception:
        pass


def run_graph_summary_inline_sync(graph: Any) -> dict[str, Any]:
    """Run GraphSummary workflow; return summary dict. No Core import in caller."""
    if graph is None:
        return {"units": [], "connections": []}
    g = (
        graph.model_dump(by_alias=True)
        if hasattr(graph, "model_dump")
        else (graph if isinstance(graph, dict) else {})
    )
    path = _CORE_WORKFLOWS_DIR / "graph_summary_single.json"
    if not path.is_file():
        return {"units": [], "connections": []}
    out = _run_sync(path, {"inject_graph": {"data": g}})
    summary = (out.get("graph_summary") or {}).get("summary")
    return summary if isinstance(summary, dict) else {"units": [], "connections": []}


async def run_graph_summary_inline(graph: Any) -> dict[str, Any]:
    if graph is None:
        return {"units": [], "connections": []}
    g = (
        graph.model_dump(by_alias=True)
        if hasattr(graph, "model_dump")
        else (graph if isinstance(graph, dict) else {})
    )
    path = _CORE_WORKFLOWS_DIR / "graph_summary_single.json"
    if not path.is_file():
        return {"units": [], "connections": []}
    out = await _run_async(path, {"inject_graph": {"data": g}})
    summary = (out.get("graph_summary") or {}).get("summary")
    return summary if isinstance(summary, dict) else {"units": [], "connections": []}


def run_units_library_source_paths_inline_sync(
    graph_summary: dict[str, Any] | None,
    implementation_links_for_types: list[str] | None,
) -> list[str]:
    """
    Run units_library_paths_single.json: UnitsLibrary → source_paths (registry already filled by run_workflow).
    Used by Workflow Designer follow-ups instead of importing units.* in the GUI layer.
    """
    gs = graph_summary if isinstance(graph_summary, dict) else {}
    link = [
        str(x).strip() for x in (implementation_links_for_types or []) if str(x).strip()
    ]
    if not link or not _UNITS_LIBRARY_PATHS_SINGLE.is_file():
        return []
    out = _run_sync(
        _UNITS_LIBRARY_PATHS_SINGLE,
        {"inject_graph_summary": {"data": gs}},
        unit_param_overrides={
            "units_library": {"implementation_links_for_types": link}
        },
    )
    raw = (out.get("units_library") or {}).get("source_paths")
    if not isinstance(raw, list):
        return []
    return [str(p) for p in raw if p is not None and str(p).strip()]


async def run_units_library_source_paths_inline(
    graph_summary: dict[str, Any] | None,
    implementation_links_for_types: list[str] | None,
) -> list[str]:
    gs = graph_summary if isinstance(graph_summary, dict) else {}
    link = [
        str(x).strip() for x in (implementation_links_for_types or []) if str(x).strip()
    ]
    if not link or not _UNITS_LIBRARY_PATHS_SINGLE.is_file():
        return []
    out = await _run_async(
        _UNITS_LIBRARY_PATHS_SINGLE,
        {"inject_graph_summary": {"data": gs}},
        unit_param_overrides={
            "units_library": {"implementation_links_for_types": link}
        },
    )
    raw = (out.get("units_library") or {}).get("source_paths")
    if not isinstance(raw, list):
        return []
    return [str(p) for p in raw if p is not None and str(p).strip()]


def run_graph_diff_inline_sync(prev_graph: Any, current_graph: Any) -> str | None:
    """Run GraphDiff workflow; return diff string or None. No Core import in caller."""
    if prev_graph is None or current_graph is None:
        return None
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
    out = _run_sync(
        path, {"inject_prev": {"data": prev}, "inject_curr": {"data": curr}}
    )
    diff = (out.get("graph_diff") or {}).get("diff")
    return str(diff).strip() or None if diff else None


async def run_graph_diff_inline(prev_graph: Any, current_graph: Any) -> str | None:
    if prev_graph is None or current_graph is None:
        return None
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
        path, {"inject_prev": {"data": prev}, "inject_curr": {"data": curr}}
    )
    diff = (out.get("graph_diff") or {}).get("diff")
    return str(diff).strip() or None if diff else None


def run_load_workflow_inline_sync(
    path_str: str, format: str | None = None
) -> tuple[dict[str, Any] | None, str | None]:
    """Run LoadWorkflow; return (graph_dict, error). No Core import in caller."""
    path = _CORE_WORKFLOWS_DIR / "load_workflow_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))
    overrides = {"load_workflow": {"format": format}} if format else {}
    out = _run_sync(
        path, {"inject_path": {"data": path_str}}, unit_param_overrides=overrides
    )
    unit_out = out.get("load_workflow") or {}
    return (unit_out.get("graph"), unit_out.get("error"))


async def run_load_workflow_inline(
    path_str: str, format: str | None = None
) -> tuple[dict[str, Any] | None, str | None]:
    path = _CORE_WORKFLOWS_DIR / "load_workflow_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))
    overrides = {"load_workflow": {"format": format}} if format else {}
    out = await _run_async(
        path, {"inject_path": {"data": path_str}}, unit_param_overrides=overrides
    )
    unit_out = out.get("load_workflow") or {}
    return (unit_out.get("graph"), unit_out.get("error"))


def run_export_workflow_inline_sync(graph: Any, format: str) -> tuple[Any, str | None]:
    """Run ExportWorkflow; return (exported dict/list, error). No Core import in caller."""
    g = (
        graph.model_dump(by_alias=True)
        if hasattr(graph, "model_dump")
        else (graph if isinstance(graph, dict) else None)
    )
    if g is None:
        return (None, "ExportWorkflow: graph missing")
    path = _CORE_WORKFLOWS_DIR / "export_workflow_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))
    out = _run_sync(
        path,
        {"inject_graph": {"data": g}},
        unit_param_overrides={"export_workflow": {"format": format}},
    )
    unit_out = out.get("export_workflow") or {}
    return (unit_out.get("exported"), unit_out.get("error"))


async def run_export_workflow_inline(graph: Any, format: str) -> tuple[Any, str | None]:
    g = (
        graph.model_dump(by_alias=True)
        if hasattr(graph, "model_dump")
        else (graph if isinstance(graph, dict) else None)
    )
    if g is None:
        return (None, "ExportWorkflow: graph missing")
    path = _CORE_WORKFLOWS_DIR / "export_workflow_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))
    out = await _run_async(
        path,
        {"inject_graph": {"data": g}},
        unit_param_overrides={"export_workflow": {"format": format}},
    )
    unit_out = out.get("export_workflow") or {}
    return (unit_out.get("exported"), unit_out.get("error"))


def run_runtime_label_inline_sync(graph: Any) -> tuple[str, bool]:
    """Run RuntimeLabel workflow; return (label, is_native). No Core import in caller."""
    if graph is None:
        return ("canonical", True)
    g = (
        graph.model_dump(by_alias=True)
        if hasattr(graph, "model_dump")
        else (graph if isinstance(graph, dict) else {})
    )
    path = _CORE_WORKFLOWS_DIR / "runtime_label_single.json"
    if not path.is_file():
        return ("canonical", True)
    out = _run_sync(path, {"inject_graph": {"data": g}})
    unit_out = out.get("runtime_label") or {}
    return (
        str(unit_out.get("label", "canonical")),
        bool(unit_out.get("is_native", True)),
    )


async def run_runtime_label_inline(graph: Any) -> tuple[str, bool]:
    if graph is None:
        return ("canonical", True)
    g = (
        graph.model_dump(by_alias=True)
        if hasattr(graph, "model_dump")
        else (graph if isinstance(graph, dict) else {})
    )
    path = _CORE_WORKFLOWS_DIR / "runtime_label_single.json"
    if not path.is_file():
        return ("canonical", True)
    out = await _run_async(path, {"inject_graph": {"data": g}})
    unit_out = out.get("runtime_label") or {}
    return (
        str(unit_out.get("label", "canonical")),
        bool(unit_out.get("is_native", True)),
    )


def run_apply_edits_inline_sync(
    graph: Any,
    edits: list[dict[str, Any]],
    graph_origin: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Run ApplyEdits workflow; return (graph_dict, error). No Core import in caller."""
    g = (
        graph.model_dump(by_alias=True)
        if hasattr(graph, "model_dump")
        else (graph if isinstance(graph, dict) else {})
    )
    path = _CORE_WORKFLOWS_DIR / "apply_edits_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))
    init: dict[str, dict[str, Any]] = {
        "inject_graph": {"data": g},
        "inject_edits": {"data": edits},
        "inject_origin": {"data": graph_origin or ""},
    }
    out = _run_sync(path, init)
    unit_out = out.get("apply_edits") or {}
    err = unit_out.get("error")
    if err:
        return (None, str(err)[:200])
    return (unit_out.get("graph"), None)


async def run_apply_edits_inline(
    graph: Any,
    edits: list[dict[str, Any]],
    graph_origin: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    g = (
        graph.model_dump(by_alias=True)
        if hasattr(graph, "model_dump")
        else (graph if isinstance(graph, dict) else {})
    )
    path = _CORE_WORKFLOWS_DIR / "apply_edits_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))
    init: dict[str, dict[str, Any]] = {
        "inject_graph": {"data": g},
        "inject_edits": {"data": edits},
        "inject_origin": {"data": graph_origin or ""},
    }
    out = await _run_async(path, init)
    unit_out = out.get("apply_edits") or {}
    err = unit_out.get("error")
    if err:
        return (None, str(err)[:200])
    return (unit_out.get("graph"), None)


def run_apply_training_config_edits_inline_sync(
    training_config: Any,
    edits: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    """Run ApplyTrainingConfigEdits workflow; return (config_dict, error). Same unit as RL Coach apply step."""
    cfg = (
        training_config.model_dump(by_alias=True)
        if hasattr(training_config, "model_dump")
        else (training_config if isinstance(training_config, dict) else {})
    )
    path = _CORE_WORKFLOWS_DIR / "apply_training_config_edits_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))
    init: dict[str, dict[str, Any]] = {
        "inject_training_config": {"data": cfg},
        "inject_edits": {"data": edits},
    }
    out = _run_sync(path, init)
    unit_out = out.get("apply_training_config_edits") or {}
    err = unit_out.get("error")
    if err:
        return (None, str(err)[:500])
    merged = unit_out.get("config")
    return (merged if isinstance(merged, dict) else None, None)


async def run_apply_training_config_edits_inline(
    training_config: Any,
    edits: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    cfg = (
        training_config.model_dump(by_alias=True)
        if hasattr(training_config, "model_dump")
        else (training_config if isinstance(training_config, dict) else {})
    )
    path = _CORE_WORKFLOWS_DIR / "apply_training_config_edits_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))
    init: dict[str, dict[str, Any]] = {
        "inject_training_config": {"data": cfg},
        "inject_edits": {"data": edits},
    }
    out = await _run_async(path, init)
    unit_out = out.get("apply_training_config_edits") or {}
    err = unit_out.get("error")
    if err:
        return (None, str(err)[:500])
    merged = unit_out.get("config")
    return (merged if isinstance(merged, dict) else None, None)


def run_normalize_graph_inline_sync(
    graph: Any, format: str = "dict"
) -> tuple[dict[str, Any] | None, str | None]:
    """Run NormalizeGraph workflow; return (graph_dict, error). No Core import in caller."""
    if graph is None:
        return (None, "NormalizeGraph: graph missing")
    g = (
        graph.model_dump(by_alias=True)
        if hasattr(graph, "model_dump")
        else (graph if isinstance(graph, dict) else {})
    )
    path = _CORE_WORKFLOWS_DIR / "normalize_graph_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))
    out = _run_sync(
        path,
        {"inject_graph": {"data": g}},
        unit_param_overrides={"normalize_graph": {"format": format}},
    )
    unit_out = out.get("normalize_graph") or {}
    return (unit_out.get("graph"), unit_out.get("error"))


async def run_normalize_graph_inline(
    graph: Any, format: str = "dict"
) -> tuple[dict[str, Any] | None, str | None]:
    if graph is None:
        return (None, "NormalizeGraph: graph missing")
    g = (
        graph.model_dump(by_alias=True)
        if hasattr(graph, "model_dump")
        else (graph if isinstance(graph, dict) else {})
    )
    path = _CORE_WORKFLOWS_DIR / "normalize_graph_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))
    out = await _run_async(
        path,
        {"inject_graph": {"data": g}},
        unit_param_overrides={"normalize_graph": {"format": format}},
    )
    unit_out = out.get("normalize_graph") or {}
    return (unit_out.get("graph"), unit_out.get("error"))


def validate_graph_to_apply_for_canvas_inline_sync(
    graph: Any,
) -> tuple[Any, str | None]:
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
    except Exception as e:
        return _fail(f"ValidateGraphToApply: model_dump failed: {e}")

    if not isinstance(g, dict):
        return _fail("ValidateGraphToApply: expected dict or model with model_dump")

    path = _CORE_WORKFLOWS_DIR / "validate_graph_to_apply_single.json"
    if not path.is_file():
        return _fail(_missing_workflow_msg(path))

    try:
        out = _run_sync(path, {"inject_graph": {"data": g}})
    except Exception as e:
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
    except Exception as e:
        return _fail(f"ValidateGraphToApply: ProcessGraph.model_validate failed: {str(e)[:200]}")


async def validate_graph_to_apply_for_canvas_inline(
    graph: Any,
) -> tuple[Any, str | None]:
    return await asyncio.to_thread(
        validate_graph_to_apply_for_canvas_inline_sync, graph
    )


def run_clean_text_for_chat_inline_sync(text: str) -> str:
    """
    Run Inject → CleanText (units/semantics/clean_text) to remove fenced markdown/code and
    JSON-like noise from message text for history and previous-turn prompts.
    """
    from units.semantics import register_semantics_units

    register_semantics_units()
    path = _agents_WORKFLOWS_DIR / "clean_text_chat_single.json"
    raw = text if isinstance(text, str) else str(text or "")
    if not path.is_file():
        return raw.strip()
    out = _run_sync(path, {"inject_text": {"data": raw}})
    unit_out = out.get("clean_text") or {}
    return str(unit_out.get("text", "") or "")


async def run_clean_text_for_chat_inline(text: str) -> str:
    return await asyncio.to_thread(run_clean_text_for_chat_inline_sync, text)
