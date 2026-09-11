"""
Run a single graph edit via the edit_workflows (one workflow per action) or apply_edits workflow (import_workflow).
Returns ProcessGraph for use by the GUI. Uses ``gui.components.workflow_tab.workflows.core_workflows`` to avoid direct Core dependency.
"""

from __future__ import annotations

from pathlib import Path

from core.schemas.primitives import (
    Data,
    JsonObject,
    WorkflowInputs,
    WorkflowOutputs,
    is_json_object,
    is_model_dumpable,
    require_json_object_from_object,
)
from core.schemas.process_graph import ProcessGraph
from gui.components.settings import _EDIT_WORKFLOWS_DIR
from runtime.run import run_workflow
from services.workflows.core_workflows import (
    run_apply_edits_inline,
    run_normalize_graph_inline,
)

# workflow_stem -> tool id under agents/tools/<tool_id>/tool.yaml (workflow filename in tool.yaml).
_TOOL_EDIT_WORKFLOW_TOOLS: dict[str, str] = {
    "add_comment": "add_comment",
    "todo_list": "todo_manager",
}


def _edit_workflow_path(workflow_stem: str) -> Path:
    """Resolve edit_*.json under edit_workflows/, or tool workflow JSON next to tool.yaml."""
    stem = (workflow_stem or "").strip()
    tool_id = _TOOL_EDIT_WORKFLOW_TOOLS.get(stem)
    if tool_id:
        from agents.tools.workflow_path import get_tool_workflow_path

        return get_tool_workflow_path(tool_id)
    return _EDIT_WORKFLOWS_DIR / f"edit_{stem}.json"


# action -> (workflow stem, unit_id). Most are 1:1; todo actions share stem todo_list → todo_manager tool workflow.
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
    "add_todo_list": ("todo_list", "todo_list"),
    "add_task": ("todo_list", "todo_list"),
    "remove_task": ("todo_list", "todo_list"),
    "remove_todo_list": ("todo_list", "todo_list"),
    "mark_completed": ("todo_list", "todo_list"),
}


def _graph_to_dict(
    graph: ProcessGraph | Data | None,
) -> Data:
    if graph is None:
        return {
            "units": [],
            "connections": [],
        }

    if isinstance(graph, dict):
        return graph

    if is_model_dumpable(graph):
        dumped = graph.model_dump(by_alias=True)

        result: Data = {}
        for key, value in dumped.items():
            result[key] = value

        return result

    return {
        "units": [],
        "connections": [],
    }




def _edit_to_params(action: str, edit: Data) -> Data:
    """Build unit_param_overrides for the edit unit from the edit dict."""
    action = (action).strip()
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
        return {
            "find_unit": edit.get("find_unit"),
            "replace_with": edit.get("replace_with"),
        }
    if action == "replace_graph":
        return {"units": edit.get("units"), "connections": edit.get("connections")}
    if action == "add_code_block":
        return {"code_block": edit.get("code_block")}
    if action == "add_comment":
        return {"info": edit.get("info"), "commenter": edit.get("commenter")}
    if action == "add_environment":
        return {"env_id": edit.get("env_id")}
    if action == "no_action":
        return {"reason": edit.get("reason")}
    if action in (
        "add_todo_list",
        "add_task",
        "remove_task",
        "remove_todo_list",
        "mark_completed",
    ):
        return {
            "action": edit.get("action", action),
            "id": edit.get("id"),
            "list_id": edit.get("list_id"),
            "todo_list_id": edit.get("todo_list_id"),
            "title": edit.get("title"),
            "text": edit.get("text"),
            "task_id": edit.get("task_id"),
            "completed": edit.get("completed"),
        }
    return {}


async def apply_edit_via_workflow(
    graph: ProcessGraph,
    edit: Data,
) -> ProcessGraph:
    """
    Apply a single graph edit by running the matching edit workflow
    or batch_edits for import_workflow.

    Returns the updated graph as ProcessGraph. Raises on failure.
    """
    graph_dict = _graph_to_dict(graph)

    graph_json: JsonObject = require_json_object_from_object(
        graph_dict,
        field="graph",
    )

    action_value = edit.get("action")

    if not isinstance(action_value, str):
        raise TypeError("Edit action must be a string")

    action = action_value.strip()

    if not action:
        raise ValueError("Edit action cannot be empty")

    if action == "import_workflow":
        out_graph, err = await run_apply_edits_inline(
            graph_dict,
            [edit],
        )

        if err:
            raise ValueError(err)

        updated = out_graph if out_graph is not None else graph_dict

        g, norm_err = await run_normalize_graph_inline(updated)

        if norm_err:
            raise ValueError(norm_err)

        return ProcessGraph.model_validate(g)

    workflow_stem, unit_id = _ACTION_WORKFLOW.get(
        action,
        ("no_action", "no_action"),
    )

    path = _edit_workflow_path(workflow_stem)

    if not path.is_file():
        path = _EDIT_WORKFLOWS_DIR / "edit_no_edit.json"
        unit_id = "no_action"

    edit_params = _edit_to_params(action, edit)

    edit_params_json: JsonObject = require_json_object_from_object(
        edit_params,
        field="edit parameters",
    )

    overrides: WorkflowInputs = {
        unit_id: edit_params_json,
    }

    initial_inputs: WorkflowInputs = {
        "inject_graph": {
            "data": graph_json,
        },
    }

    outputs: WorkflowOutputs = run_workflow(
        path,
        initial_inputs=initial_inputs,
        unit_param_overrides=overrides,
        format="dict",
    )

    unit_output = outputs.get(unit_id)

    if not is_json_object(unit_output):
        updated = graph_dict
    else:
        updated_value = unit_output.get("graph")

        if is_json_object(updated_value):
            updated = updated_value
        else:
            updated = graph_dict

    g, norm_err = await run_normalize_graph_inline(updated)

    if norm_err:
        raise ValueError(norm_err)

    return ProcessGraph.model_validate(g)



__all__ = ["apply_edit_via_workflow"]
