"""Workflow Designer–specific chat workflow execution (dev: run current canvas graph in memory)."""
from __future__ import annotations

from typing import Any, Callable

from core.schemas.process_graph import ProcessGraph
from gui.chat.context.llm_prompt_inspector import attach_llm_prompt_debug_from_outputs
from gui.chat.utils import collect_workflow_errors
from gui.components.workflow_tab.workflows.core_workflows import run_normalize_graph
from runtime.executor import GraphExecutor


def run_current_graph(
    graph: ProcessGraph | dict[str, Any] | None,
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    stream_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Run the given graph in memory (no file). Same contract as run_agent_workflow:
    returns merge_response.data shape (reply, result, status, ...) for GUI.
    Use in -dev mode to run the current designer graph with the chat message.
    stream_callback: optional; each LLM token chunk is passed here (called from executor thread).
    """
    if graph is None:
        return {"reply": "", "result": {}, "status": {}, "graph": None, "diff": "", "parser_output": None, "run_output": {}, "report_output": {}, "grep_output": {}, "formulas_calc_output": {}, "formulas_calc_error": "", "delegate_request": {}, "delegate_request_error": "", "workflow_errors": [("run_current_graph", "No graph loaded.")]}
    try:
        from units.data_bi import register_data_bi_units
        register_data_bi_units()
    except Exception:
        pass
    from units.register_env_agnostic import register_env_agnostic_units
    register_env_agnostic_units()
    try:
        from units.canonical import register_canonical_units
        register_canonical_units()
    except Exception:
        pass
    try:
        from units.rag import register_rag_units

        register_rag_units()
    except Exception:
        pass

    if isinstance(graph, ProcessGraph):
        pg = graph
    else:
        g_dict = graph if isinstance(graph, dict) else (graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else None)
        if g_dict is None:
            return {"reply": "", "result": {}, "status": {}, "graph": None, "diff": "", "parser_output": None, "run_output": {}, "report_output": {}, "grep_output": {}, "formulas_calc_output": {}, "formulas_calc_error": "", "delegate_request": {}, "delegate_request_error": "", "workflow_errors": [("run_current_graph", "Graph must be dict or ProcessGraph.")]}
        g_norm, norm_err = run_normalize_graph(g_dict, format="dict")
        if norm_err or g_norm is None:
            return {"reply": "", "result": {}, "status": {}, "graph": None, "diff": "", "parser_output": None, "run_output": {}, "report_output": {}, "grep_output": {}, "formulas_calc_output": {}, "formulas_calc_error": "", "delegate_request": {}, "delegate_request_error": "", "workflow_errors": [("run_current_graph", norm_err or "Normalize failed")]}
        pg = ProcessGraph.model_validate(g_norm)

    if unit_param_overrides:
        new_units = []
        for u in pg.units:
            over = unit_param_overrides.get(u.id)
            if over and isinstance(over, dict):
                new_units.append(u.model_copy(update={"params": {**(u.params or {}), **over}}))
            else:
                new_units.append(u)
        pg = pg.model_copy(update={"units": new_units})

    # Re-register canonical so Aggregate/Prompt have step_fn (normalized graph may have loaded n8n and overwritten).
    try:
        from units.canonical import register_canonical_units
        register_canonical_units()
    except Exception:
        pass
    try:
        from units.rag import register_rag_units

        register_rag_units()
    except Exception:
        pass
    executor = GraphExecutor(pg)
    outputs = executor.execute(
        initial_inputs=initial_inputs or {},
        stream_callback=stream_callback,
    )

    data = (outputs.get("merge_response") or {}).get("data")
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
    # Fallback: if merge_response didn't get reply, use llm_agent.action so chat always shows the response
    reply_val = data.get("reply")
    if not (isinstance(reply_val, str) and reply_val.strip()):
        llm_out = (outputs.get("llm_agent") or {})
        if isinstance(llm_out.get("action"), str) and llm_out["action"].strip():
            data = {**data, "reply": llm_out["action"].strip()}
    data["workflow_errors"] = collect_workflow_errors(outputs)
    attach_llm_prompt_debug_from_outputs(outputs, data)
    return data
