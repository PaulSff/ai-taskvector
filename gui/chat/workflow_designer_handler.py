"""
Workflow Designer assistant handler: build initial_inputs and run assistant_workflow.json.

Chat runs the workflow via run_assistant_workflow(); prompt and response handling live in the workflow.
The user's message is passed in initial_inputs["inject_user_message"]["data"] and is required for the LLM.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Literal

from assistants.prompts import WORKFLOW_DESIGNER_RETRY_USER
from core.schemas.process_graph import ProcessGraph
from assistants.roles.workflow_designer.workflow_inputs import (
    build_assistant_workflow_initial_inputs,
    default_wf_language_hint,
)
from gui.components.workflow_tab.workflows.core_workflows import (
    run_graph_summary,
    run_normalize_graph,
    run_runtime_label,
)
from runtime.executor import GraphExecutor
from runtime.run import run_workflow, WorkflowTimeoutError

from assistants.roles import WORKFLOW_DESIGNER_ROLE_ID
from assistants.roles.workflow_path import get_role_chat_workflow_path
from assistants.tools.workflow_path import get_tool_workflow_path
from gui.chat.llm_prompt_inspector import attach_llm_prompt_debug_from_outputs
from gui.chat.workflow_run_utils import collect_workflow_errors
from gui.components.settings import (
    get_contribution_is_allowed,
    get_rag_format_max_chars,
    get_rag_format_snippet_max,
    get_rag_min_score,
    get_workflow_designer_llm_generation_options,
    get_workflow_designer_prompt_path,
    get_workflow_designer_rag_top_k,
)

# Main WD graph: ``assistants/roles/workflow_designer/role.yaml`` ``chat.workflow``
ASSISTANT_WORKFLOW_PATH = get_role_chat_workflow_path(WORKFLOW_DESIGNER_ROLE_ID)
WEB_SEARCH_WORKFLOW_PATH = get_tool_workflow_path("web_search")
BROWSER_WORKFLOW_PATH = get_tool_workflow_path("browse")
GITHUB_GET_WORKFLOW_PATH = get_tool_workflow_path("github")

# Timeout for workflow run so we don't hang when a unit (LLM, RAG, etc.) never responds. Timeout then drop.
DEFAULT_EXECUTION_TIMEOUT_S = 300.0


def get_runtime_for_prompts(graph: Any) -> Literal["native", "external"]:
    """Read runtime from graph (set on import); fallback to RuntimeLabel workflow when missing."""
    if graph is None:
        return "external"
    r = graph.get("runtime") if isinstance(graph, dict) else getattr(graph, "runtime", None)
    if r in ("native", "external"):
        return r
    _, is_native = run_runtime_label(graph)
    return "native" if is_native else "external"


def run_workflow_with_errors(
    path: str | Path,
    initial_inputs: dict[str, dict[str, Any]] | None = None,
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    format: str | None = "dict",
    execution_timeout_s: float | None = None,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """
    Run a workflow and return (outputs, errors). Error collection is done here so
    callers (e.g. chat) only need to display errors (toast), not import collect_workflow_errors.
    execution_timeout_s: if set, abort after this many seconds (raises WorkflowTimeoutError).
    """
    outputs = run_workflow(
        path,
        initial_inputs=initial_inputs or {},
        unit_param_overrides=unit_param_overrides,
        format=format,
        execution_timeout_s=execution_timeout_s,
    )
    return outputs, collect_workflow_errors(outputs)


def refresh_last_apply_result_after_canvas_apply(
    prev: dict[str, Any] | None,
    graph: Any,
    *,
    supplement_summary: str = "",
) -> dict[str, Any]:
    """
    Rebuild last_apply_result after the GUI applies the workflow graph to the canvas.

    The chat may inject todo_list tasks (add_unit connections/params, import review, code-block
    review) after the assistant
    workflow returns; ApplyEdits' last_apply_result then describes a graph *without* those tasks.
    Refreshing keeps inject_turn_state / inject_last_edit_block and graph_after aligned with
    graph_ref for the post-apply follow-up run (e.g. mark_completed on the injected task id).
    """
    prev = prev or {}
    g_dict: dict[str, Any]
    if graph is not None and hasattr(graph, "model_dump"):
        g_dict = graph.model_dump(by_alias=True)
    elif isinstance(graph, dict):
        g_dict = graph
    else:
        g_dict = {"units": [], "connections": []}

    base = (prev.get("edits_summary") or "").strip()
    sup = (supplement_summary or "").strip()
    if sup:
        edits_summary = f"{base}; {sup}" if base else sup
    else:
        edits_summary = base or "applied"

    return {
        "attempted": True,
        "success": True,
        "error": None,
        "edits_summary": edits_summary,
        "graph_after": run_graph_summary(g_dict),
    }


def build_self_correction_retry_inputs(
    failed_apply_result: dict[str, Any],
    graph: Any,
    recent_changes: str | None,
    runtime: str = "native",
    coding_is_allowed: bool = True,
    contribution_is_allowed: bool | None = None,
    previous_turn: str = "",
    language_hint: str | None = None,
    session_language: str = "",
) -> dict[str, dict[str, Any]]:
    """
    Build initial_inputs for a same-turn self-correction retry when apply failed.
    Uses WORKFLOW_DESIGNER_RETRY_USER as the user message and failed_apply_result so
    inject_last_edit_block contains the error and self-correction instructions.
    Caller (chat) runs the workflow with these inputs and then applies the result or shows toast.
    previous_turn: optional prior user+assistant summary (same as main workflow) so the model keeps context.
    """
    err_str = str(failed_apply_result.get("error", "Unknown"))[:500]
    if language_hint is None:
        language_hint = default_wf_language_hint(session_language)
    lang = (language_hint or "English (en)").strip() or "English (en)"
    retry_user_message = WORKFLOW_DESIGNER_RETRY_USER.format(error=err_str, language=lang)
    _contrib = get_contribution_is_allowed() if contribution_is_allowed is None else contribution_is_allowed
    return build_assistant_workflow_initial_inputs(
        retry_user_message,
        graph,
        failed_apply_result,
        recent_changes,
        follow_up_context="",
        runtime=runtime,
        coding_is_allowed=coding_is_allowed,
        contribution_is_allowed=_contrib,
        previous_turn=(previous_turn or "").strip(),
        language_hint=lang,
        session_language=session_language,
    )


def build_assistant_workflow_unit_param_overrides(
    provider: str,
    cfg: dict[str, Any],
    report_output_dir: str | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Build unit_param_overrides for run_workflow(assistant_workflow.json) from app_settings + role/tool YAML.
    llm_agent (model_name, provider, host, options), rag_search (top_k; graph JSON uses ``settings.*`` / ``role.*``
    refs resolved in ``GraphExecutor`` via ``app_settings_param``), rag_filter / format_rag (same numeric caps as
    ``get_rag_*`` / ``get_workflow_designer_rag_top_k`` from role/tool YAML), prompt_llm (template_path),
    report (output_dir).

    RAG numbers match ``rag_context.get_rag_context*`` / ``rag_context_workflow.json`` (tool/role refs).
    """
    model_name = (cfg.get("model") or "").strip() or "llama3.2"
    host = (cfg.get("host") or "http://127.0.0.1:11434").strip()
    overrides: dict[str, dict[str, Any]] = {
        "llm_agent": {
            "model_name": model_name,
            "provider": (provider or "ollama").strip(),
            "host": host,
            "options": dict(get_workflow_designer_llm_generation_options()),
        },
        "rag_search": {
            "top_k": get_workflow_designer_rag_top_k(),
        },
        "rag_filter": {
            "value": get_rag_min_score(),
        },
        "format_rag": {
            "max_chars": get_rag_format_max_chars(),
            "snippet_max": get_rag_format_snippet_max(),
        },
        "prompt_llm": {
            "template_path": str(get_workflow_designer_prompt_path()),
        },
    }
    if report_output_dir:
        overrides["report"] = {"output_dir": report_output_dir}
    return overrides


def run_assistant_workflow(
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    execution_timeout_s: float | None = DEFAULT_EXECUTION_TIMEOUT_S,
    stream_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Run assistant_workflow.json and return merge_response.data for the GUI.
    Returns dict with keys: reply, result, status, graph, diff, parser_output, run_output.
    Raises WorkflowTimeoutError if execution exceeds execution_timeout_s (timeout then drop).
    Registers data_bi units (Filter) so the workflow's rag_filter unit is available.
    stream_callback: optional; each LLM token chunk is passed here (called from executor thread).
    """
    try:
        from units.data_bi import register_data_bi_units
        register_data_bi_units()
    except Exception:
        pass
    outputs = run_workflow(
        ASSISTANT_WORKFLOW_PATH,
        initial_inputs=initial_inputs,
        unit_param_overrides=unit_param_overrides,
        format="dict",
        execution_timeout_s=execution_timeout_s,
        stream_callback=stream_callback,
    )
    data = (outputs.get("merge_response") or {}).get("data")
    # Build return shape; if merge_response.data is missing or not a dict, still try to show LLM reply from llm_agent
    if not isinstance(data, dict):
        data = {"reply": "", "result": {}, "status": {}, "graph": None, "diff": "", "parser_output": None, "run_output": {}, "report_output": {}, "grep_output": {}}
    if "parser_output" not in data:
        data = {**data, "parser_output": None}
    if "run_output" not in data:
        data = {**data, "run_output": {}}
    if "report_output" not in data:
        data = {**data, "report_output": {}}
    if "grep_output" not in data:
        data = {**data, "grep_output": {}}
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


def run_current_graph(
    graph: ProcessGraph | dict[str, Any] | None,
    initial_inputs: dict[str, dict[str, Any]],
    unit_param_overrides: dict[str, dict[str, Any]] | None = None,
    stream_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Run the given graph in memory (no file). Same contract as run_assistant_workflow:
    returns merge_response.data shape (reply, result, status, ...) for GUI.
    Use in -dev mode to run the current designer graph with the chat message.
    stream_callback: optional; each LLM token chunk is passed here (called from executor thread).
    """
    if graph is None:
        return {"reply": "", "result": {}, "status": {}, "graph": None, "diff": "", "parser_output": None, "run_output": {}, "report_output": {}, "grep_output": {}, "workflow_errors": [("run_current_graph", "No graph loaded.")]}
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

    if isinstance(graph, ProcessGraph):
        pg = graph
    else:
        g_dict = graph if isinstance(graph, dict) else (graph.model_dump(by_alias=True) if hasattr(graph, "model_dump") else None)
        if g_dict is None:
            return {"reply": "", "result": {}, "status": {}, "graph": None, "diff": "", "parser_output": None, "run_output": {}, "report_output": {}, "grep_output": {}, "workflow_errors": [("run_current_graph", "Graph must be dict or ProcessGraph.")]}
        g_norm, norm_err = run_normalize_graph(g_dict, format="dict")
        if norm_err or g_norm is None:
            return {"reply": "", "result": {}, "status": {}, "graph": None, "diff": "", "parser_output": None, "run_output": {}, "report_output": {}, "grep_output": {}, "workflow_errors": [("run_current_graph", norm_err or "Normalize failed")]}
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
    executor = GraphExecutor(pg)
    outputs = executor.execute(
        initial_inputs=initial_inputs or {},
        stream_callback=stream_callback,
    )

    data = (outputs.get("merge_response") or {}).get("data")
    if not isinstance(data, dict):
        data = {"reply": "", "result": {}, "status": {}, "graph": None, "diff": "", "parser_output": None, "run_output": {}, "report_output": {}, "grep_output": {}}
    if "parser_output" not in data:
        data = {**data, "parser_output": None}
    if "run_output" not in data:
        data = {**data, "run_output": {}}
    if "report_output" not in data:
        data = {**data, "report_output": {}}
    if "grep_output" not in data:
        data = {**data, "grep_output": {}}
    # Fallback: if merge_response didn't get reply, use llm_agent.action so chat always shows the response
    reply_val = data.get("reply")
    if not (isinstance(reply_val, str) and reply_val.strip()):
        llm_out = (outputs.get("llm_agent") or {})
        if isinstance(llm_out.get("action"), str) and llm_out["action"].strip():
            data = {**data, "reply": llm_out["action"].strip()}
    data["workflow_errors"] = collect_workflow_errors(outputs)
    attach_llm_prompt_debug_from_outputs(outputs, data)
    return data
