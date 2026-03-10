"""
Run a single graph edit via the edit_workflows (one workflow per action) or batch_edits (import_workflow).
Returns ProcessGraph for use by the GUI.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.normalizer import to_process_graph
from core.schemas.process_graph import ProcessGraph

from runtime.run import run_workflow

_EDIT_WORKFLOWS_DIR = Path(__file__).resolve().parent

# action -> (workflow stem, unit_id). Most are 1:1; todo actions share edit_todo_list / todo_list.
_ACTION_WORKFLOW: dict[str, tuple[str, str]] = {
    "add_unit": ("add_unit", "add_unit"),
    "add_pipeline": ("add_pipeline", "add_pipeline"),
    "remove_unit": ("remove_unit", "remove_unit"),
    "connect": ("connect", "connect"),
    "disconnect": ("disconnect", "disconnect"),
    "replace_unit": ("replace_unit", "replace_unit"),
    "replace_graph": ("replace_graph", "replace_graph"),
    "add_code_block": ("add_code_block", "add_code_block"),
    "add_comment": ("add_comment", "add_comment"),
    "add_environment": ("add_environment", "add_environment"),
    "no_edit": ("no_edit", "no_edit"),
    "add_todo_list": ("todo_list", "todo_list"),
    "add_task": ("todo_list", "todo_list"),
    "remove_task": ("todo_list", "todo_list"),
    "remove_todo_list": ("todo_list", "todo_list"),
    "mark_completed": ("todo_list", "todo_list"),
}


def _graph_to_dict(graph: ProcessGraph | dict[str, Any]) -> dict[str, Any]:
    if graph is None:
        return {"units": [], "connections": []}
    if hasattr(graph, "model_dump"):
        return graph.model_dump(by_alias=True)
    return dict(graph) if isinstance(graph, dict) else {"units": [], "connections": []}


def _edit_to_params(action: str, edit: dict[str, Any]) -> dict[str, Any]:
    """Build unit_param_overrides for the edit unit from the edit dict."""
    action = (action or "no_edit").strip()
    if action == "add_unit":
        return {"unit": edit.get("unit")}
    if action == "add_pipeline":
        return {"pipeline": edit.get("pipeline")}
    if action == "remove_unit":
        return {"unit_id": edit.get("unit_id")}
    if action == "connect":
        return {
            "from_id": edit.get("from"),
            "to_id": edit.get("to"),
            "from_port": edit.get("from_port"),
            "to_port": edit.get("to_port"),
        }
    if action == "disconnect":
        return {
            "from_id": edit.get("from"),
            "to_id": edit.get("to"),
            "from_port": edit.get("from_port"),
            "to_port": edit.get("to_port"),
        }
    if action == "replace_unit":
        return {"find_unit": edit.get("find_unit"), "replace_with": edit.get("replace_with")}
    if action == "replace_graph":
        return {"units": edit.get("units"), "connections": edit.get("connections")}
    if action == "add_code_block":
        return {"code_block": edit.get("code_block")}
    if action == "add_comment":
        return {"info": edit.get("info"), "commenter": edit.get("commenter")}
    if action == "add_environment":
        return {"env_id": edit.get("env_id")}
    if action == "no_edit":
        return {"reason": edit.get("reason")}
    if action in ("add_todo_list", "add_task", "remove_task", "remove_todo_list", "mark_completed"):
        return {
            "action": edit.get("action", action),
            "title": edit.get("title"),
            "text": edit.get("text"),
            "task_id": edit.get("task_id"),
            "completed": edit.get("completed"),
        }
    return {}


def apply_edit_via_workflow(
    graph: ProcessGraph | dict[str, Any],
    edit: dict[str, Any],
) -> ProcessGraph:
    """
    Apply a single graph edit by running the matching edit workflow (or batch_edits for import_workflow).
    Returns the updated graph as ProcessGraph. Raises on failure.
    """
    graph_dict = _graph_to_dict(graph)
    action = (edit.get("action") or "no_edit").strip()

    if action == "import_workflow":
        from core.graph.batch_edits import apply_workflow_edits
        result = apply_workflow_edits(graph_dict, [edit])
        if not result.get("success"):
            raise ValueError(result.get("error") or "Apply failed")
        out = result.get("graph")
        return to_process_graph(out if out is not None else graph_dict, format="dict")

    workflow_stem, unit_id = _ACTION_WORKFLOW.get(action, ("no_edit", "no_edit"))
    path = _EDIT_WORKFLOWS_DIR / f"edit_{workflow_stem}.json"
    if not path.is_file():
        path = _EDIT_WORKFLOWS_DIR / "edit_no_edit.json"
        unit_id = "no_edit"

    overrides = {unit_id: _edit_to_params(action, edit)}
    outputs = run_workflow(
        path,
        initial_inputs={"inject_graph": {"data": graph_dict}},
        unit_param_overrides=overrides,
        format="dict",
    )
    updated = outputs.get(unit_id, {}).get("graph")
    if updated is None:
        updated = graph_dict
    return to_process_graph(updated, format="dict")


__all__ = ["apply_edit_via_workflow"]
