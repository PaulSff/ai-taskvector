"""
Run a single graph edit via an edit workflow (Inject -> edit unit) when a workflow JSON exists.
Falls back to apply_graph_edit for import_unit/import_workflow or when no workflow file is found.
Validation remains in graph_edits.apply_graph_edit.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runtime.executor import GraphExecutor
from core.normalizer import to_process_graph
from core.schemas.process_graph import ProcessGraph

from core.graph.graph_edits import apply_graph_edit

_EDIT_WORKFLOWS_DIR = Path(__file__).resolve().parent / "edit_workflows"
_EDIT_UNIT_ID = "edit"
_INJECT_UNIT_ID = "inject"


def _ensure_graph_edit_units_registered() -> None:
    """Ensure Inject and edit units are registered so workflow load and execution work."""
    try:
        from units.env_agnostic.graph_edit import register_graph_edit_flow_units
        register_graph_edit_flow_units()
    except Exception:
        pass


def run_edit_flow(current: dict[str, Any], edit: dict[str, Any]) -> dict[str, Any]:
    """
    Apply one graph edit by running the corresponding edit workflow when available.
    current: graph dict (as from GUI/session).
    edit: GraphEdit-shaped dict (action, unit, from_id, to_id, ...).
    Returns updated graph dict. Raises on validation errors (from apply_graph_edit inside the flow).
    """
    action = (edit.get("action") or "").strip()
    if action in ("import_unit", "import_workflow"):
        return apply_graph_edit(current, edit)

    _ensure_graph_edit_units_registered()
    workflow_path = _EDIT_WORKFLOWS_DIR / f"{action}.json"
    if not workflow_path.is_file():
        return apply_graph_edit(current, edit)

    raw = json.loads(workflow_path.read_text(encoding="utf-8"))
    process_graph = to_process_graph(raw, format="dict")
    if not isinstance(process_graph, ProcessGraph):
        return apply_graph_edit(current, edit)

    edit_unit = process_graph.get_unit(_EDIT_UNIT_ID)
    if not edit_unit:
        return apply_graph_edit(current, edit)

    params = dict(edit)
    params.pop("action", None)
    edit_unit.params.update(params)

    executor = GraphExecutor(process_graph)
    initial_inputs = {_INJECT_UNIT_ID: {"graph": current}}
    outputs = executor.execute(initial_inputs=initial_inputs)
    out = outputs.get(_EDIT_UNIT_ID, {}).get("graph")
    if out is None:
        return apply_graph_edit(current, edit)
    return out
