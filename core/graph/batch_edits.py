"""
Apply a list of graph edits to a graph dict (batch application). Standalone (no dependency on assistants).
Used by the ApplyEdits unit and the workflow designer.
import_workflow is resolved from file/URL; import_unit (RAG catalog) is no longer supported.
"""
from __future__ import annotations

from typing import Any, get_args

from core.normalizer.runtime_detector import external_runtime_or_none
from core.schemas.agent_node import RL_GYM_NODE_TYPE

from core.graph.graph_edits import GraphEditAction, apply_graph_edit
from core.graph.import_resolver import resolve_import_edits

_GRAPH_EDIT_ACTIONS: frozenset[str] = frozenset(get_args(GraphEditAction))
RL_ORACLE_NODE_TYPE = "RLOracle"

# Generic error messages (no assistants.prompts dependency)
_ERR_RLGYM_EXTERNAL = "RLGym is for native (canonical) runtime only; use RLOracle for {runtime}."
_ERR_RLORACLE_NATIVE = "RLOracle is for external runtimes only; use RLGym for native runtime."


def _edit_adds_rlgym(edit: dict[str, Any]) -> bool:
    """True if this edit would add or replace with an RLGym unit (native runtime only)."""
    if not isinstance(edit, dict):
        return False
    action = edit.get("action")
    if action == "add_unit":
        unit = edit.get("unit") or {}
        return (unit.get("type") or "").strip() == RL_GYM_NODE_TYPE
    if action == "replace_unit":
        repl = edit.get("replace_with") or {}
        return (repl.get("type") or "").strip() == RL_GYM_NODE_TYPE
    if action == "add_pipeline":
        pipeline = edit.get("pipeline") or {}
        return (pipeline.get("type") or "").strip() == RL_GYM_NODE_TYPE
    return False


def _edit_adds_rloracle(edit: dict[str, Any]) -> bool:
    """True if this edit would add or replace with an RLOracle unit (external runtime only)."""
    if not isinstance(edit, dict):
        return False
    action = edit.get("action")
    if action == "add_unit":
        unit = edit.get("unit") or {}
        return (unit.get("type") or "").strip() == RL_ORACLE_NODE_TYPE
    if action == "replace_unit":
        repl = edit.get("replace_with") or {}
        return (repl.get("type") or "").strip() == RL_ORACLE_NODE_TYPE
    if action == "add_pipeline":
        pipeline = edit.get("pipeline") or {}
        return (pipeline.get("type") or "").strip() == RL_ORACLE_NODE_TYPE
    return False


def apply_workflow_edits(
    current: dict[str, Any] | None,
    edits: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Apply a list of graph edits sequentially to a graph dict.
    Only edits whose action is in GraphEditAction are applied; others are skipped.
    import_workflow is resolved from file/URL (no RAG).
    Returns dict: {success: bool, graph: dict, error: str | None}
    """
    if current is None:
        current = {"units": [], "connections": []}
    graph: dict[str, Any] = dict(current)

    for edit in edits:
        if not isinstance(edit, dict) or edit.get("action") not in _GRAPH_EDIT_ACTIONS:
            continue
        if edit.get("action") in (None, "no_edit"):
            continue

        if edit.get("action") == "import_workflow":
            resolved = resolve_import_edits([edit], graph)
            to_apply = resolved
        else:
            to_apply = [edit]

        for sub_edit in to_apply:
            if not isinstance(sub_edit, dict) or sub_edit.get("action") in (None, "no_edit"):
                continue
            runtime = external_runtime_or_none(graph)
            if runtime is not None and _edit_adds_rlgym(sub_edit):
                return {
                    "success": False,
                    "graph": graph,
                    "error": _ERR_RLGYM_EXTERNAL.format(runtime=runtime),
                }
            if runtime is None and _edit_adds_rloracle(sub_edit):
                return {
                    "success": False,
                    "graph": graph,
                    "error": _ERR_RLORACLE_NATIVE,
                }
            try:
                graph = apply_graph_edit(graph, sub_edit)
            except Exception as ex:
                return {
                    "success": False,
                    "graph": graph,
                    "error": str(ex)[:500],
                }

    return {"success": True, "graph": graph, "error": None}
