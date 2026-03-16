"""
Run core operations via small workflows so the GUI does not depend on Core directly.

All functions run a workflow (Inject -> unit), return the unit output. Uses runtime.run.run_workflow.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

_WORKFLOW_DIR = Path(__file__).resolve().parent


def _run(path: Path, initial_inputs: dict[str, dict[str, Any]], unit_param_overrides: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    from runtime.run import run_workflow
    register_env_agnostic_units()
    return run_workflow(path, initial_inputs=initial_inputs, unit_param_overrides=unit_param_overrides or {}, format="dict")


def register_env_agnostic_units() -> None:
    try:
        from units.canonical import register_canonical_units
        register_canonical_units()
    except Exception:
        pass


def run_graph_summary(graph: dict[str, Any] | Any) -> dict[str, Any]:
    """Run GraphSummary workflow; return summary dict. No Core import in caller."""
    if graph is None:
        return {"units": [], "connections": []}
    g = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else (graph if isinstance(graph, dict) else {})
    path = _WORKFLOW_DIR / "graph_summary_single.json"
    if not path.is_file():
        from core.graph import graph_summary as _gs
        return _gs(g)
    out = _run(path, {"inject_graph": {"data": g}})
    summary = (out.get("graph_summary") or {}).get("summary")
    return summary if isinstance(summary, dict) else {"units": [], "connections": []}


def run_graph_diff(prev_graph: dict[str, Any] | Any, current_graph: dict[str, Any] | Any) -> str | None:
    """Run GraphDiff workflow; return diff string or None. No Core import in caller."""
    if prev_graph is None or current_graph is None:
        return None
    prev = prev_graph.model_dump(by_alias=True) if hasattr(prev_graph, "model_dump") else (prev_graph if isinstance(prev_graph, dict) else {})
    curr = current_graph.model_dump(by_alias=True) if hasattr(current_graph, "model_dump") else (current_graph if isinstance(current_graph, dict) else {})
    path = _WORKFLOW_DIR / "graph_diff_single.json"
    if not path.is_file():
        from core.graph import graph_diff as _gd
        return _gd(prev, curr)
    out = _run(path, {"inject_prev": {"data": prev}, "inject_curr": {"data": curr}})
    diff = (out.get("graph_diff") or {}).get("diff")
    return str(diff).strip() or None if diff else None


def run_load_workflow(path_str: str, format: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    """Run LoadWorkflow; return (graph_dict, error). No Core import in caller."""
    path = _WORKFLOW_DIR / "load_workflow_single.json"
    if not path.is_file():
        from core.normalizer import load_process_graph_from_file
        try:
            pg = load_process_graph_from_file(path_str, format=format)
            return (pg.model_dump(by_alias=True), None)
        except Exception as e:
            return (None, str(e)[:200])
    overrides = {"load_workflow": {"format": format}} if format else {}
    out = _run(path, {"inject_path": {"data": path_str}}, unit_param_overrides=overrides)
    unit_out = out.get("load_workflow") or {}
    return (unit_out.get("graph"), unit_out.get("error"))


def run_export_workflow(graph: dict[str, Any] | Any, format: str) -> tuple[Any, str | None]:
    """Run ExportWorkflow; return (exported dict/list, error). No Core import in caller."""
    g = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else (graph if isinstance(graph, dict) else None)
    if g is None:
        return (None, "ExportWorkflow: graph missing")
    path = _WORKFLOW_DIR / "export_workflow_single.json"
    if not path.is_file():
        from core.normalizer import to_process_graph
        from core.normalizer.export import from_process_graph
        try:
            pg = to_process_graph(g, format="dict")
            raw = from_process_graph(pg, format=format)
            return (raw, None)
        except Exception as e:
            return (None, str(e)[:200])
    out = _run(path, {"inject_graph": {"data": g}}, unit_param_overrides={"export_workflow": {"format": format}})
    unit_out = out.get("export_workflow") or {}
    return (unit_out.get("exported"), unit_out.get("error"))


def run_runtime_label(graph: dict[str, Any] | Any) -> tuple[str, bool]:
    """Run RuntimeLabel workflow; return (label, is_native). No Core import in caller."""
    if graph is None:
        return ("canonical", True)
    g = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else (graph if isinstance(graph, dict) else {})
    path = _WORKFLOW_DIR / "runtime_label_single.json"
    if not path.is_file():
        from core.normalizer.runtime_detector import is_canonical_runtime, runtime_label
        return (runtime_label(g), is_canonical_runtime(g))
    out = _run(path, {"inject_graph": {"data": g}})
    unit_out = out.get("runtime_label") or {}
    return (str(unit_out.get("label", "canonical")), bool(unit_out.get("is_native", True)))


def run_apply_edits(graph: dict[str, Any] | Any, edits: list[dict[str, Any]], graph_origin: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    """Run ApplyEdits workflow; return (graph_dict, error). No Core import in caller."""
    g = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else (graph if isinstance(graph, dict) else {})
    path = _WORKFLOW_DIR / "apply_edits_single.json"
    if not path.is_file():
        from core.graph.batch_edits import apply_workflow_edits
        result = apply_workflow_edits(g, edits)
        if not result.get("success"):
            return (None, (result.get("error") or "Apply failed")[:200])
        return (result.get("graph"), None)
    init: dict[str, dict[str, Any]] = {
        "inject_graph": {"data": g},
        "inject_edits": {"data": edits},
        "inject_origin": {"data": graph_origin or ""},
    }
    out = _run(path, init)
    unit_out = out.get("apply_edits") or {}
    err = unit_out.get("error")
    if err:
        return (None, str(err)[:200])
    return (unit_out.get("graph"), None)


def run_normalize_graph(graph: dict[str, Any] | Any, format: str = "dict") -> tuple[dict[str, Any] | None, str | None]:
    """Run NormalizeGraph workflow; return (graph_dict, error). No Core import in caller."""
    if graph is None:
        return (None, "NormalizeGraph: graph missing")
    g = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else (graph if isinstance(graph, dict) else {})
    path = _WORKFLOW_DIR / "normalize_graph_single.json"
    if not path.is_file():
        from core.normalizer import to_process_graph
        try:
            pg = to_process_graph(g, format=format)
            return (pg.model_dump(by_alias=True), None)
        except Exception as e:
            return (None, str(e)[:200])
    out = _run(path, {"inject_graph": {"data": g}}, unit_param_overrides={"normalize_graph": {"format": format}})
    unit_out = out.get("normalize_graph") or {}
    return (unit_out.get("graph"), unit_out.get("error"))
