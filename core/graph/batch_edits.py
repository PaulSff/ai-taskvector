"""
Apply a list of graph edits to a graph dict (batch application). Standalone (no dependency on agents).
Used by the ApplyEdits unit and the workflow designer.
import_workflow is resolved from file/URL; import_unit (RAG catalog) is no longer supported.
"""

from __future__ import annotations

from typing import get_args

from core.graph.graph_edits import GraphEditAction, apply_graph_edit
from core.graph.import_resolver import resolve_import_edits
from core.normalizer.runtime_detector import external_runtime_or_none
from core.schemas.agent_node import RL_GYM_NODE_TYPE

from .graph_edits import JSONValue

_GRAPH_EDIT_ACTIONS: frozenset[str] = frozenset(get_args(GraphEditAction))
RL_ORACLE_NODE_TYPE = "RLOracle"

# Generic error messages (no agents.prompts dependency)
_ERR_RLGYM_EXTERNAL = (
    "RLGym is for native (canonical) runtime only; use RLOracle for {runtime}."
)
_ERR_RLORACLE_NATIVE = (
    "RLOracle is for external runtimes only; use RLGym for native runtime."
)


def _unit_type(value: JSONValue | None) -> str:
    if not isinstance(value, dict):
        return ""

    unit_type = value.get("type")
    return unit_type.strip() if isinstance(unit_type, str) else ""


def _edit_adds_rlgym(edit: dict[str, JSONValue]) -> bool:
    """True if this edit would add or replace with an RLGym unit."""
    action = edit.get("action")

    if action == "add_unit":
        return _unit_type(edit.get("unit")) == RL_GYM_NODE_TYPE

    if action == "replace_unit":
        return _unit_type(edit.get("replace_with")) == RL_GYM_NODE_TYPE

    if action == "add_pipeline":
        return _unit_type(edit.get("pipeline")) == RL_GYM_NODE_TYPE

    return False


def _edit_adds_rloracle(edit: dict[str, JSONValue]) -> bool:
    """True if this edit would add or replace with an RLOracle unit."""
    action = edit.get("action")

    if action == "add_unit":
        return _unit_type(edit.get("unit")) == RL_ORACLE_NODE_TYPE

    if action == "replace_unit":
        return _unit_type(edit.get("replace_with")) == RL_ORACLE_NODE_TYPE

    if action == "add_pipeline":
        return _unit_type(edit.get("pipeline")) == RL_ORACLE_NODE_TYPE

    return False


def apply_workflow_edits(
    current: dict[str, JSONValue] | None,
    edits: list[dict[str, JSONValue]],
    *,
    allowed_actions: frozenset[str] | None = None,
) -> dict[str, JSONValue]:
    """
    Apply a list of graph edits sequentially to a graph dict.
    Only edits whose action is in GraphEditAction are applied; others are skipped.
    When ``allowed_actions`` is set, only those actions are applied (must still be in GraphEditAction).
    import_workflow is resolved from file/URL (no RAG).
    Returns dict: {success: bool, graph: dict, error: str | None}
    """
    if current is None:
        current = {"units": [], "connections": []}
    graph: dict[str, JSONValue] = dict(current)

    for edit in edits:
        act = edit.get("action")

        if act not in _GRAPH_EDIT_ACTIONS:
            continue

        if act in (None, "no_edit"):
            continue

        if allowed_actions is not None and act not in allowed_actions:
            continue


        if edit.get("action") == "import_workflow":
            resolved = resolve_import_edits([edit], graph)
            to_apply = resolved
        else:
            to_apply = [edit]

        for sub_edit in to_apply:
            if sub_edit.get("action") in (None, "no_edit"):
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
            except (ValueError, TypeError) as ex:
                return {
                    "success": False,
                    "graph": graph,
                    "error": str(ex)[:500],
                }


    return {"success": True, "graph": graph, "error": None}
