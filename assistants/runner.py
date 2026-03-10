"""
Assistant workflow runner: builds initial_inputs and unit overrides from named parameters,
then calls the generic runtime.run.run_workflow. Extracts response, result, status for the caller.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from assistants.process_assistant import graph_summary
from runtime.run import run_workflow


_ASSISTANT_WORKFLOW_PATH = Path(__file__).resolve().parent / "assistant_workflow.json"


def run_assistant_workflow(
    user_message: str,
    current_graph: Any,
    *,
    workflow_path: str | Path | None = None,
    last_apply_result: dict[str, Any] | None = None,
    units_library: str = "",
    rag_context: str = "",
    turn_state: str = "",
    recent_changes_block: str = "",
    last_edit_block: str = "",
    llm_params_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run the assistant workflow once. Builds initial_inputs for each Inject from arguments,
    calls generic run_workflow, returns outputs + extracted response, result, status.

    All parameters are passed through; no hardcoded defaults except empty string / "Last action: none." for turn_state.
    """
    path = Path(workflow_path) if workflow_path else _ASSISTANT_WORKFLOW_PATH

    graph_summary_dict = graph_summary(current_graph)
    if hasattr(current_graph, "model_dump"):
        graph_dict = current_graph.model_dump(by_alias=True)
    else:
        graph_dict = dict(current_graph) if current_graph else {"units": [], "connections": []}

    initial_inputs = {
        "inject_user_message": {"data": user_message or ""},
        "inject_graph_summary": {"data": graph_summary_dict},
        "inject_units_library": {"data": units_library or ""},
        "inject_rag_context": {"data": rag_context or ""},
        "inject_turn_state": {"data": turn_state or "Last action: none."},
        "inject_recent_changes_block": {"data": recent_changes_block or ""},
        "inject_last_edit_block": {"data": last_edit_block or ""},
        "inject_graph": {"data": graph_dict},
    }

    unit_param_overrides = None
    if llm_params_override:
        unit_param_overrides = {"llm_agent": llm_params_override}

    outputs = run_workflow(
        path,
        initial_inputs=initial_inputs,
        unit_param_overrides=unit_param_overrides,
        format="dict",
    )

    response = ""
    if "llm_agent" in outputs and isinstance(outputs["llm_agent"], dict):
        response = (outputs["llm_agent"].get("action") or "") if isinstance(outputs["llm_agent"].get("action"), str) else str(outputs["llm_agent"].get("action", ""))

    result: dict[str, Any] = {}
    status: dict[str, Any] = {}
    if "process" in outputs and isinstance(outputs["process"], dict):
        result = outputs["process"].get("result") or {}
        status = outputs["process"].get("status") or {}

    return {
        "outputs": outputs,
        "response": response,
        "result": result,
        "status": status,
    }
