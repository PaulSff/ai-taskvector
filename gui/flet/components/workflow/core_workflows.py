"""
Run core operations via small workflows so the GUI does not depend on Core directly.

All functions run a workflow (Inject -> unit), return the unit output. Uses runtime.run.run_workflow.
JSON workflow files under ``core/`` and ``assistants/`` are required; there is no fallback to
importing ``core`` when a file is missing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

_WORKFLOW_DIR = Path(__file__).resolve().parent
_CORE_DIR = _WORKFLOW_DIR / "core"
_ASSISTANTS_DIR = _WORKFLOW_DIR / "assistants"

_UNITS_LIBRARY_PATHS_SINGLE = _ASSISTANTS_DIR / "units_library_paths_single.json"


def _missing_workflow_msg(path: Path) -> str:
    return f"Required workflow file not found: {path}"


def _run(path: Path, initial_inputs: dict[str, dict[str, Any]], unit_param_overrides: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    from runtime.run import run_workflow

    return run_workflow(path, initial_inputs=initial_inputs, unit_param_overrides=unit_param_overrides or {}, format="dict")


def register_env_agnostic_units() -> None:
    """Backward-compatible name: full registry bootstrap (same as run_workflow startup)."""
    try:
        from units.registry import ensure_full_unit_registry

        ensure_full_unit_registry()
    except Exception:
        pass


def run_graph_summary(graph: dict[str, Any] | Any) -> dict[str, Any]:
    """Run GraphSummary workflow; return summary dict. No Core import in caller."""
    if graph is None:
        return {"units": [], "connections": []}
    g = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else (graph if isinstance(graph, dict) else {})
    path = _CORE_DIR / "graph_summary_single.json"
    if not path.is_file():
        return {"units": [], "connections": []}
    out = _run(path, {"inject_graph": {"data": g}})
    summary = (out.get("graph_summary") or {}).get("summary")
    return summary if isinstance(summary, dict) else {"units": [], "connections": []}


def run_units_library_source_paths(
    graph_summary: dict[str, Any] | None,
    implementation_links_for_types: list[str] | None,
) -> list[str]:
    """
    Run units_library_paths_single.json: UnitsLibrary → source_paths (registry already filled by run_workflow).
    Used by Workflow Designer follow-ups instead of importing units.* in the GUI layer.
    """
    gs = graph_summary if isinstance(graph_summary, dict) else {}
    link = [str(x).strip() for x in (implementation_links_for_types or []) if str(x).strip()]
    if not link or not _UNITS_LIBRARY_PATHS_SINGLE.is_file():
        return []
    out = _run(
        _UNITS_LIBRARY_PATHS_SINGLE,
        {"inject_graph_summary": {"data": gs}},
        unit_param_overrides={"units_library": {"implementation_links_for_types": link}},
    )
    raw = (out.get("units_library") or {}).get("source_paths")
    if not isinstance(raw, list):
        return []
    return [str(p) for p in raw if p is not None and str(p).strip()]


def run_graph_diff(prev_graph: dict[str, Any] | Any, current_graph: dict[str, Any] | Any) -> str | None:
    """Run GraphDiff workflow; return diff string or None. No Core import in caller."""
    if prev_graph is None or current_graph is None:
        return None
    prev = prev_graph.model_dump(by_alias=True) if hasattr(prev_graph, "model_dump") else (prev_graph if isinstance(prev_graph, dict) else {})
    curr = current_graph.model_dump(by_alias=True) if hasattr(current_graph, "model_dump") else (current_graph if isinstance(current_graph, dict) else {})
    path = _CORE_DIR / "graph_diff_single.json"
    if not path.is_file():
        return None
    out = _run(path, {"inject_prev": {"data": prev}, "inject_curr": {"data": curr}})
    diff = (out.get("graph_diff") or {}).get("diff")
    return str(diff).strip() or None if diff else None


def run_load_workflow(path_str: str, format: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    """Run LoadWorkflow; return (graph_dict, error). No Core import in caller."""
    path = _CORE_DIR / "load_workflow_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))
    overrides = {"load_workflow": {"format": format}} if format else {}
    out = _run(path, {"inject_path": {"data": path_str}}, unit_param_overrides=overrides)
    unit_out = out.get("load_workflow") or {}
    return (unit_out.get("graph"), unit_out.get("error"))


def run_export_workflow(graph: dict[str, Any] | Any, format: str) -> tuple[Any, str | None]:
    """Run ExportWorkflow; return (exported dict/list, error). No Core import in caller."""
    g = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else (graph if isinstance(graph, dict) else None)
    if g is None:
        return (None, "ExportWorkflow: graph missing")
    path = _CORE_DIR / "export_workflow_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))
    out = _run(path, {"inject_graph": {"data": g}}, unit_param_overrides={"export_workflow": {"format": format}})
    unit_out = out.get("export_workflow") or {}
    return (unit_out.get("exported"), unit_out.get("error"))


def run_runtime_label(graph: dict[str, Any] | Any) -> tuple[str, bool]:
    """Run RuntimeLabel workflow; return (label, is_native). No Core import in caller."""
    if graph is None:
        return ("canonical", True)
    g = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else (graph if isinstance(graph, dict) else {})
    path = _CORE_DIR / "runtime_label_single.json"
    if not path.is_file():
        return ("canonical", True)
    out = _run(path, {"inject_graph": {"data": g}})
    unit_out = out.get("runtime_label") or {}
    return (str(unit_out.get("label", "canonical")), bool(unit_out.get("is_native", True)))


def run_apply_edits(graph: dict[str, Any] | Any, edits: list[dict[str, Any]], graph_origin: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    """Run ApplyEdits workflow; return (graph_dict, error). No Core import in caller."""
    g = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else (graph if isinstance(graph, dict) else {})
    path = _CORE_DIR / "apply_edits_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))
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
    path = _CORE_DIR / "normalize_graph_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))
    out = _run(path, {"inject_graph": {"data": g}}, unit_param_overrides={"normalize_graph": {"format": format}})
    unit_out = out.get("normalize_graph") or {}
    return (unit_out.get("graph"), unit_out.get("error"))


def validate_graph_to_apply_for_canvas(graph: Any) -> tuple[Any, str | None]:
    """
    Run ``validate_graph_to_apply_single.json`` (Inject → ValidateGraphToApply), then build
    ``ProcessGraph`` for ``set_graph`` / canvas apply.

    Use from Flet chat instead of ``ProcessGraph.model_validate`` on raw assistant output dicts.
    """
    if graph is None:
        return (None, "ValidateGraphToApply: graph missing")
    g = graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else graph
    if not isinstance(g, dict):
        return (None, "ValidateGraphToApply: expected dict or model with model_dump")
    path = _CORE_DIR / "validate_graph_to_apply_single.json"
    if not path.is_file():
        return (None, _missing_workflow_msg(path))
    out = _run(path, {"inject_graph": {"data": g}})
    unit_out = out.get("validate_graph_to_apply") or {}
    err = unit_out.get("error")
    if err:
        return (None, str(err))
    gd = unit_out.get("graph")
    if not isinstance(gd, dict):
        return (None, "ValidateGraphToApply: no graph in workflow output")
    from core.schemas.process_graph import ProcessGraph

    try:
        return (ProcessGraph.model_validate(gd), None)
    except Exception as e:
        return (None, str(e)[:200])


def run_clean_text_for_chat(text: str) -> str:
    """
    Run Inject → CleanText (units/semantics/clean_text) to remove fenced markdown/code and
    JSON-like noise from message text for history and previous-turn prompts.

    Uses ``assistants/clean_text_chat_single.json`` (max_chars=0, min_block_len=1). Callers avoid importing
    ``units`` or ``process_agent`` directly.
    """
    from units.semantics import register_semantics_units

    register_semantics_units()
    path = _ASSISTANTS_DIR / "clean_text_chat_single.json"
    raw = text if isinstance(text, str) else str(text or "")
    if not path.is_file():
        return raw.strip()
    out = _run(path, {"inject_text": {"data": raw}})
    unit_out = out.get("clean_text") or {}
    return str(unit_out.get("text", "") or "")
