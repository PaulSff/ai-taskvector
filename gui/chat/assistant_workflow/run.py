"""Run a role chat workflow file and normalize ``merge_response.data`` for the GUI."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from gui.chat.context.llm_prompt_inspector import attach_llm_prompt_debug_from_outputs
from gui.chat.utils import collect_workflow_errors
from runtime.run import run_workflow

from .paths import ASSISTANT_WORKFLOW_PATH, DEFAULT_EXECUTION_TIMEOUT_S


def run_assistant_workflow(
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    execution_timeout_s: float | None = DEFAULT_EXECUTION_TIMEOUT_S,
    stream_callback: Callable[[str], None] | None = None,
    *,
    workflow_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    Run a role chat workflow JSON and return merge_response.data for the GUI.
    Returns dict with keys: reply, result, status, graph, diff, parser_output, run_output.
    Raises WorkflowTimeoutError if execution exceeds execution_timeout_s (timeout then drop).
    Registers data_bi units (Filter) so the workflow's rag_filter unit is available.
    stream_callback: optional; each LLM token chunk is passed here (called from executor thread).
    workflow_path: optional; defaults to Workflow Designer's ``assistant_workflow.json``.
    """
    try:
        from units.data_bi import register_data_bi_units
        register_data_bi_units()
    except Exception:
        pass
    wp = Path(workflow_path).resolve() if workflow_path is not None else ASSISTANT_WORKFLOW_PATH
    outputs = run_workflow(
        wp,
        initial_inputs=initial_inputs,
        unit_param_overrides=unit_param_overrides,
        format="dict",
        execution_timeout_s=execution_timeout_s,
        stream_callback=stream_callback,
    )
    data = (outputs.get("merge_response") or {}).get("data")
    # Build return shape; if merge_response.data is missing or not a dict, still try to show LLM reply from llm_agent
    if not isinstance(data, dict):
        data = {"reply": "", "result": {}, "status": {}, "graph": None, "diff": "", "parser_output": None, "run_output": {}, "report_output": {}, "grep_output": {}, "formulas_calc_output": {}, "formulas_calc_error": "", "delegate_request": {}, "delegate_request_error": ""}
    if "parser_output" not in data:
        data = {**data, "parser_output": None}
    if "run_output" not in data:
        data = {**data, "run_output": {}}
    if "report_output" not in data:
        data = {**data, "report_output": {}}
    if "grep_output" not in data:
        data = {**data, "grep_output": {}}
    if "formulas_calc_output" not in data:
        data = {**data, "formulas_calc_output": {}}
    if "formulas_calc_error" not in data:
        data = {**data, "formulas_calc_error": ""}
    if "delegate_request" not in data:
        data = {**data, "delegate_request": {}}
    if "delegate_request_error" not in data:
        data = {**data, "delegate_request_error": ""}
    # Fallback: if merge_response didn't get reply (e.g. connection order / missing data), use llm_agent.action so chat always shows the response
    reply_val = data.get("reply")
    if not (isinstance(reply_val, str) and reply_val.strip()):
        llm_out = (outputs.get("llm_agent") or {})
        if isinstance(llm_out.get("action"), str) and llm_out["action"].strip():
            data = {**data, "reply": llm_out["action"].strip()}
    data["workflow_errors"] = collect_workflow_errors(outputs)
    attach_llm_prompt_debug_from_outputs(outputs, data)
    return data


# Note: assistant_workflow.json wires merge_errors → debug_errors only; the GUI does not read
# merge_errors. Per-unit error ports (e.g. process) are collected via collect_workflow_errors(outputs).
